"""LTP (Lists, Tables, Properties) layer of the MS-PST file format.

Built on top of the NDB layer (ndb.py): the Heap-on-Node (HN) is a heap of variously-sized
allocations inside one node's data; a BTree-on-Heap (BTH) is a small BTree stored in that heap,
mapping keys to fixed-size records; a Property Context (PC) is a BTH keyed by MAPI property id,
used to store a node's own properties (e.g. a message's Subject, a folder's display name).

Also implements Table Context (TC) - folder hierarchy/contents tables and per-message
recipient/attachment tables - which is layered on the same HN/BTH machinery as PC but with its own
on-disk row-matrix shape ([MS-PST] 2.3.4).

Multi-block heaps (a HN whose data spans more than one NDB block) are supported for reading the
page map, since large PCs are pushed to subnodes at the NDB layer before that would matter for
most single-block heaps in practice - see HID bit layout note below.
"""

import struct
from dataclasses import dataclass

from .ndb import NID_TYPE_HID, PSTFile, nid_type

HN_SIGNATURE = 0xEC
BTYPE_PC = 0xBC
BTYPE_TC = 0x7C
BTH_SIGNATURE = 0xB5


def _hid_parts(hid: int) -> tuple:
    """[MS-PST] 2.3.3.1 HID: hidType (5 bits), hidIndex (11 bits, 1-based), hidBlockIndex (16 bits)."""
    hid_type_ = hid & 0x1F
    hid_index = (hid >> 5) & 0x7FF
    hid_block_index = (hid >> 16) & 0xFFFF
    return hid_type_, hid_index, hid_block_index


@dataclass
class HeapOnNode:
    """A single-node heap: one or more NDB blocks, each with its own allocation-offset table."""

    b_client_sig: int
    hid_user_root: int
    pages: list  # list of (block_bytes, rgib_alloc) - rgib_alloc[i] gives the start offset of
    #              allocation i+1 (1-based) in block_bytes; the last entry is the end-of-data marker.

    def item(self, hid: int) -> bytes:
        hid_type_, hid_index, hid_block_index = _hid_parts(hid)
        if hid_type_ != NID_TYPE_HID:
            raise ValueError(f"Not a HID (type={hid_type_:#x}): {hid:#x}")
        if hid_index == 0:
            return b""
        block_bytes, rgib_alloc = self.pages[hid_block_index]
        start = rgib_alloc[hid_index - 1]
        end = rgib_alloc[hid_index]
        return block_bytes[start:end]


def _read_page_map(block: bytes, ib_hnpm: int) -> list:
    c_alloc = struct.unpack_from("<H", block, ib_hnpm)[0]
    n_entries = c_alloc + 1
    return list(struct.unpack_from(f"<{n_entries}H", block, ib_hnpm + 4))


def parse_heap(pst: PSTFile, bid_data: int) -> HeapOnNode:
    """Read and parse the (possibly multi-block) heap for a node's primary data block.

    A multi-block HN is stored as one NDB block per heap "page" (not concatenated - each block has
    its own trailing page map, verified against data/personal-email-backup.pst's 14-block contents
    table heap). ibHnpm (the page map's start offset) is always a block's first 2 bytes, in every
    block; bSig/bClientSig/hidUserRoot are only present in block 0 (HNHDR) - later blocks (HNPAGEHDR)
    start their allocation data immediately after ibHnpm, with no per-block equivalent of those
    node-wide fields.
    """
    blocks = pst.read_block_parts(bid_data)
    first = blocks[0]
    if len(first) < 12 or first[2] != HN_SIGNATURE:
        raise ValueError(f"Bad HN signature {first[2] if len(first) > 2 else None!r} (expected {HN_SIGNATURE:#x})")
    b_client_sig = first[3]
    hid_user_root = struct.unpack_from("<I", first, 4)[0]

    pages = []
    for block in blocks:
        ib_hnpm = struct.unpack_from("<H", block, 0)[0]
        pages.append((block, _read_page_map(block, ib_hnpm)))
    return HeapOnNode(b_client_sig=b_client_sig, hid_user_root=hid_user_root, pages=pages)


@dataclass
class BTHRecord:
    key: bytes
    value: bytes


def read_bth(heap: HeapOnNode, hid: int, cb_key: int, cb_ent: int, b_idx_levels: int) -> list:
    """[MS-PST] 2.3.2 BTree-on-Heap: read every record of the (possibly nested) BTH rooted at hid.

    Only the BTHHEADER (see read_bth_header) carries bIdxLevels/type info - individual
    leaf/intermediate BTH nodes are plain flat arrays with no per-node header of their own, so the
    depth has to be threaded through from the caller rather than read back off each node's bytes.
    """
    if hid == 0:
        return []
    raw = heap.item(hid)
    if not raw:
        return []
    if b_idx_levels == 0:
        rec_size = cb_key + cb_ent
        return [BTHRecord(key=raw[i : i + cb_key], value=raw[i + cb_key : i + rec_size]) for i in range(0, len(raw), rec_size)]

    # Intermediate BTH page: entries are (key[cb_key], hidNextLevel[4]).
    entry_size = cb_key + 4
    records = []
    for i in range(0, len(raw), entry_size):
        child_hid = struct.unpack_from("<I", raw, i + cb_key)[0]
        records.extend(read_bth(heap, child_hid, cb_key, cb_ent, b_idx_levels - 1))
    return records


def read_bth_header(heap: HeapOnNode) -> tuple:
    """Read the BTHHEADER at the heap's user root. Returns (cb_key, cb_ent, b_idx_levels, hid_root)."""
    raw = heap.item(heap.hid_user_root)
    if len(raw) < 8 or raw[0] != BTH_SIGNATURE:
        raise ValueError(f"Bad BTHHEADER signature at hidUserRoot {heap.hid_user_root:#x}")
    cb_key, cb_ent, b_idx_levels = raw[1], raw[2], raw[3]
    hid_root = struct.unpack_from("<I", raw, 4)[0]
    return cb_key, cb_ent, b_idx_levels, hid_root


def resolve_hnid(pst: PSTFile, heap: HeapOnNode, hnid: int, sub_bid: int) -> bytes:
    """Resolve a dwValueHnid (PC column value / TC per-cell value) to its actual bytes.

    hnid's low 5 bits (its NID type) disambiguate a heap HID from a subnode-BTree NID, per
    [MS-PST] 2.3.3.3 / Variable-sized Data. Not used for a TC's hnidRows itself (see
    `_resolve_row_matrix`) - a multi-block row matrix needs block-boundary-aware truncation that a
    plain single-blob resolve would corrupt.
    """
    type_bits = nid_type(hnid)
    if type_bits == NID_TYPE_HID:
        return heap.item(hnid)
    # Subnode reference: hnid's low 4 bytes *are* the local NID under this node's subnode BTree.
    if sub_bid == 0:
        raise ValueError(f"Property value references subnode NID {hnid:#x} but node has no subnode BTree")
    result = pst.read_subnode(sub_bid, hnid)
    if result is None:
        raise KeyError(f"Subnode NID {hnid:#x} not found")
    bid_data, _bid_sub = result
    return pst.read_block(bid_data)


# --- Property Context (PC) - [MS-PST] 2.3.3 ----------------------------------------------

FIXED_SIZE_TYPES = {
    0x0002: 2,  # PtypInteger16
    0x0003: 4,  # PtypInteger32
    0x0004: 4,  # PtypFloating32
    0x0005: 8,  # PtypFloating64
    0x000A: 4,  # PtypErrorCode
    0x000B: 1,  # PtypBoolean (occupies 1 byte of the 4-byte slot)
    0x0014: 8,  # PtypInteger64
    0x0040: 8,  # PtypTime
}
# Anything not listed above (PtypString, PtypString8, PtypBinary, PtypGuid, PtypObject, and all
# PtypMultiple* types) is variable-size and always resolved via HNID (HID or subnode NID).


@dataclass
class PSTProperty:
    """A single decoded-to-bytes MAPI property. prop_type disambiguates how to further decode
    `value` (e.g. PtypString/0x1f is UTF-16LE text, PtypString8/0x1e is codepage-dependent text,
    PtypBinary/0x102 could be either depending on the specific property - see pst/messages.py)."""

    prop_type: int
    value: bytes


def read_property_context(pst: PSTFile, bid_data: int, bid_sub: int) -> dict:
    """Return {prop_id: PSTProperty} for every property stored in a node's Property Context.

    Values are returned as raw bytes (post inline/HID/subnode resolution) alongside their MAPI
    property type - decoding into Python types (str/int/datetime/...) is the caller's job, since
    e.g. a PtypBinary value (like PidTagHtmlBody) needs different handling than a PtypString one.
    """
    heap = parse_heap(pst, bid_data)
    if heap.b_client_sig != BTYPE_PC:
        raise ValueError(f"Node's HN bClientSig is {heap.b_client_sig:#x}, not a Property Context ({BTYPE_PC:#x})")
    cb_key, cb_ent, b_idx_levels, hid_root = read_bth_header(heap)
    if cb_key != 2:
        raise ValueError(f"Unexpected PC BTH cbKey {cb_key} (expected 2 for a 2-byte wPropId)")

    props = {}
    for rec in read_bth(heap, hid_root, cb_key, cb_ent, b_idx_levels):
        # PC BTH Record ([MS-PST] 2.3.3.3): BTH key = wPropId (cb_key=2); BTH value = wPropType(2) +
        # dwValueHnid(4) (cb_ent=6). The BTH key is NOT repeated inside the value.
        prop_id = struct.unpack_from("<H", rec.key, 0)[0]
        prop_type = struct.unpack_from("<H", rec.value, 0)[0]
        raw_value = rec.value[2:6]
        fixed_size = FIXED_SIZE_TYPES.get(prop_type)
        if fixed_size is not None and fixed_size <= 4:
            value = raw_value[:fixed_size]
        else:
            hnid = struct.unpack_from("<I", raw_value, 0)[0]
            value = resolve_hnid(pst, heap, hnid, bid_sub)
        props[prop_id] = PSTProperty(prop_type=prop_type, value=value)
    return props


# --- Table Context (TC) - [MS-PST] 2.3.4 --------------------------------------------------


@dataclass
class TCColumn:
    prop_id: int
    prop_type: int
    ib_data: int
    cb_data: int
    i_bit: int


def _read_tcinfo(heap: HeapOnNode) -> tuple:
    """Read the TCINFO header at the heap's user root. Returns (rgib, hnidRows, [TCColumn, ...])."""
    raw = heap.item(heap.hid_user_root)
    if len(raw) < 22 or raw[0] != BTYPE_TC:
        raise ValueError(f"Bad TCINFO signature at hidUserRoot {heap.hid_user_root:#x}")
    c_cols = raw[1]
    rgib = struct.unpack_from("<4H", raw, 2)
    _hid_row_index, hnid_rows, _hid_index = struct.unpack_from("<III", raw, 10)

    columns = []
    off = 22
    for _ in range(c_cols):
        tag = struct.unpack_from("<I", raw, off)[0]
        ib_data = struct.unpack_from("<H", raw, off + 4)[0]
        cb_data, i_bit = raw[off + 6], raw[off + 7]
        columns.append(TCColumn(prop_id=tag >> 16, prop_type=tag & 0xFFFF, ib_data=ib_data, cb_data=cb_data, i_bit=i_bit))
        off += 8
    return rgib, hnid_rows, columns


def _resolve_row_matrix(pst: PSTFile, heap: HeapOnNode, hnid_rows: int, sub_bid: int, row_width: int) -> bytes:
    """Resolve a TC's hnidRows to the concatenated, row-aligned Row Matrix bytes.

    A heap-inline row matrix (small table) is exact - no padding, so `heap.item` is enough. A
    subnode-stored row matrix (large table) is split across ~8KB NDB blocks, and - verified against
    data/personal-email-backup.pst's 262-row "Me" folder contents table - each block reserves any
    leftover space after its last whole row as padding rather than starting the next row there
    (e.g. an 8176-byte block held exactly 62 rows of 130 bytes, with 116 trailing pad bytes).
    Simply concatenating raw blocks (as `resolve_hnid`/`PSTFile.read_block` do, correctly, for
    every other HNID use) would splice that padding into the middle of the row stream, so each
    block is truncated to a whole number of rows before joining.
    """
    if nid_type(hnid_rows) == NID_TYPE_HID:
        return heap.item(hnid_rows)
    if sub_bid == 0:
        raise ValueError(f"Row Matrix references subnode NID {hnid_rows:#x} but node has no subnode BTree")
    result = pst.read_subnode(sub_bid, hnid_rows)
    if result is None:
        raise KeyError(f"Row Matrix subnode NID {hnid_rows:#x} not found")
    bid_data, _bid_sub = result
    parts = pst.read_block_parts(bid_data)
    trimmed = [part[: len(part) - (len(part) % row_width)] for part in parts]
    return b"".join(trimmed)


def read_table_context(pst: PSTFile, bid_data: int, bid_sub: int) -> list:
    """Return one {prop_id: raw_bytes} dict per row of a node's Table Context.

    Used for folder hierarchy/contents tables and per-message recipient/attachment tables. Reads
    every row directly out of the Row Matrix rather than resolving the Row ID BTH (hidRowIndex) -
    full enumeration doesn't need dwRowID -> row-index lookups, only "every row, in any order".

    Every column is decoded for every row regardless of the Cell Existence Bitmap: real PST files
    (verified against data/personal-email-backup.pst) don't reliably set the CEB bit for columns
    that do hold meaningful data - e.g. the mandatory dwRowID/dwRowVer columns come back with their
    CEB bit clear despite holding real values - so treating a clear bit as authoritative "absent"
    would drop real data. An actually-unset fixed column just decodes as its type's zero value
    (0/False/""), which is an acceptable trade-off for this read-only import use case.
    """
    heap = parse_heap(pst, bid_data)
    if heap.b_client_sig != BTYPE_TC:
        raise ValueError(f"Node's HN bClientSig is {heap.b_client_sig:#x}, not a Table Context ({BTYPE_TC:#x})")
    rgib, hnid_rows, columns = _read_tcinfo(heap)
    row_width = rgib[3]
    if row_width == 0 or hnid_rows == 0:
        return []

    row_matrix = _resolve_row_matrix(pst, heap, hnid_rows, bid_sub, row_width)

    rows = []
    for r in range(0, len(row_matrix), row_width):
        row = row_matrix[r : r + row_width]
        props = {}
        for col in columns:
            raw_field = row[col.ib_data : col.ib_data + col.cb_data]
            if FIXED_SIZE_TYPES.get(col.prop_type) == col.cb_data:
                props[col.prop_id] = raw_field
            else:
                hnid = struct.unpack_from("<I", raw_field, 0)[0]
                props[col.prop_id] = resolve_hnid(pst, heap, hnid, bid_sub)
        rows.append(props)
    return rows
