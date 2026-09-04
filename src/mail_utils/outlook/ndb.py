"""NDB (Node Database) layer of the MS-PST file format.

Implements just enough of [MS-PST] section 2.2.2 to open a PST file - Unicode (wVer >= 23) or ANSI
(wVer 14/15) - and walk its Node BTree (NBT) and Block BTree (BBT), and resolve any NID to its fully
decoded/decompressed byte stream - including multi-block data (XBLOCK/XXBLOCK) and subnodes
(SLBLOCK/SIBLOCK).

ANSI and Unicode share the same overall page/block/BTree *shape*; the only difference is the width
of a BID/IB (4 bytes ANSI, 8 bytes Unicode) and everywhere that width propagates: BREF, BTENTRY,
BBTENTRY, NBTENTRY, SLENTRY, SIENTRY, an XBLOCK/XXBLOCK's BID array, and BLOCKTRAILER's own `bid`
field - plus the HEADER/ROOT structures, which differ in more ways than just field width (extra
ANSI-only/Unicode-only fields, different field order). Every width-sensitive function below takes an
explicit `is_ansi: bool` rather than inferring it per-call, so a caller can't accidentally mix formats
mid-read. Exact byte offsets for both variants were verified against the real [MS-PST] specification
(learn.microsoft.com/en-us/openspecs/office_file_formats/ms-pst) rather than derived from memory,
given the cost of a silently-wrong offset against real archive data - see T0021.

The higher LTP layer (ltp.py: Heap-on-Node, BTree-on-Heap, Property/Table Context) needs no
ANSI-specific changes at all: HIDs (heap-internal handles) are always 32-bit in both PST formats, and
everything LTP reads comes back through this module's already-format-aware `PSTFile` methods.

Deliberately out of scope: NDB_CRYPT_CYCLIC encoding, CRC/signature verification (advisory only in
the spec - skipped here), and write support (this app is read-only by design, see CLAUDE.md).
"""

import struct
from dataclasses import dataclass
from pathlib import Path

PAGE_SIZE = 512
HEADER_READ_SIZE = 564  # generous upper bound covering both the 512-byte ANSI and 564-byte Unicode header

# [MS-PST] 2.2.2.7.1 PAGETRAILER ptype values
PTYPE_BBT = 0x80
PTYPE_NBT = 0x81

# [MS-PST] 2.2.2.6 bCryptMethod values
NDB_CRYPT_NONE = 0x00
NDB_CRYPT_PERMUTE = 0x01
NDB_CRYPT_CYCLIC = 0x02

# [MS-PST] 5.1 Permutative encoding - mpbbCrypt is 3 concatenated 256-byte tables: mpbbR
# (encode), mpbbS (unused by CryptPermute), mpbbI (decode). Only mpbbI is needed here.
# fmt: off
_MPBB_CRYPT = [
    65, 54, 19, 98, 168, 33, 110, 187, 244, 22, 204, 4, 127, 100, 232, 93,
    30, 242, 203, 42, 116, 197, 94, 53, 210, 149, 71, 158, 150, 45, 154, 136,
    76, 125, 132, 63, 219, 172, 49, 182, 72, 95, 246, 196, 216, 57, 139, 231,
    35, 59, 56, 142, 200, 193, 223, 37, 177, 32, 165, 70, 96, 78, 156, 251,
    170, 211, 86, 81, 69, 124, 85, 0, 7, 201, 43, 157, 133, 155, 9, 160,
    143, 173, 179, 15, 99, 171, 137, 75, 215, 167, 21, 90, 113, 102, 66, 191,
    38, 74, 107, 152, 250, 234, 119, 83, 178, 112, 5, 44, 253, 89, 58, 134,
    126, 206, 6, 235, 130, 120, 87, 199, 141, 67, 175, 180, 28, 212, 91, 205,
    226, 233, 39, 79, 195, 8, 114, 128, 207, 176, 239, 245, 40, 109, 190, 48,
    77, 52, 146, 213, 14, 60, 34, 50, 229, 228, 249, 159, 194, 209, 10, 129,
    18, 225, 238, 145, 131, 118, 227, 151, 230, 97, 138, 23, 121, 164, 183, 220,
    144, 122, 92, 140, 2, 166, 202, 105, 222, 80, 26, 17, 147, 185, 82, 135,
    88, 252, 237, 29, 55, 73, 27, 106, 224, 41, 51, 153, 189, 108, 217, 148,
    243, 64, 84, 111, 240, 198, 115, 184, 214, 62, 101, 24, 68, 31, 221, 103,
    16, 241, 12, 25, 236, 174, 3, 161, 20, 123, 169, 11, 255, 248, 163, 192,
    162, 1, 247, 46, 188, 36, 104, 117, 13, 254, 186, 47, 181, 208, 218, 61,
    20, 83, 15, 86, 179, 200, 122, 156, 235, 101, 72, 23, 22, 21, 159, 2,
    204, 84, 124, 131, 0, 13, 12, 11, 162, 98, 168, 118, 219, 217, 237, 199,
    197, 164, 220, 172, 133, 116, 214, 208, 167, 155, 174, 154, 150, 113, 102, 195,
    99, 153, 184, 221, 115, 146, 142, 132, 125, 165, 94, 209, 93, 147, 177, 87,
    81, 80, 128, 137, 82, 148, 79, 78, 10, 107, 188, 141, 127, 110, 71, 70,
    65, 64, 68, 1, 17, 203, 3, 63, 247, 244, 225, 169, 143, 60, 58, 249,
    251, 240, 25, 48, 130, 9, 46, 201, 157, 160, 134, 73, 238, 111, 77, 109,
    196, 45, 129, 52, 37, 135, 27, 136, 170, 252, 6, 161, 18, 56, 253, 76,
    66, 114, 100, 19, 55, 36, 106, 117, 119, 67, 255, 230, 180, 75, 54, 92,
    228, 216, 53, 61, 69, 185, 44, 236, 183, 49, 43, 41, 7, 104, 163, 14,
    105, 123, 24, 158, 33, 57, 190, 40, 26, 91, 120, 245, 35, 202, 42, 176,
    175, 62, 254, 4, 140, 231, 229, 152, 50, 149, 211, 246, 74, 232, 166, 234,
    233, 243, 213, 47, 112, 32, 242, 31, 5, 103, 173, 85, 16, 206, 205, 227,
    39, 59, 218, 186, 215, 194, 38, 212, 145, 29, 210, 28, 34, 51, 248, 250,
    241, 90, 239, 207, 144, 182, 139, 181, 189, 192, 191, 8, 151, 30, 108, 226,
    97, 224, 198, 193, 89, 171, 187, 88, 222, 95, 223, 96, 121, 126, 178, 138,
    71, 241, 180, 230, 11, 106, 114, 72, 133, 78, 158, 235, 226, 248, 148, 83,
    224, 187, 160, 2, 232, 90, 9, 171, 219, 227, 186, 198, 124, 195, 16, 221,
    57, 5, 150, 48, 245, 55, 96, 130, 140, 201, 19, 74, 107, 29, 243, 251,
    143, 38, 151, 202, 145, 23, 1, 196, 50, 45, 110, 49, 149, 255, 217, 35,
    209, 0, 94, 121, 220, 68, 59, 26, 40, 197, 97, 87, 32, 144, 61, 131,
    185, 67, 190, 103, 210, 70, 66, 118, 192, 109, 91, 126, 178, 15, 22, 41,
    60, 169, 3, 84, 13, 218, 93, 223, 246, 183, 199, 98, 205, 141, 6, 211,
    105, 92, 134, 214, 20, 247, 165, 102, 117, 172, 177, 233, 69, 33, 112, 12,
    135, 159, 116, 164, 34, 76, 111, 191, 31, 86, 170, 46, 179, 120, 51, 80,
    176, 163, 146, 188, 207, 25, 28, 167, 99, 203, 30, 77, 62, 75, 27, 155,
    79, 231, 240, 238, 173, 58, 181, 89, 4, 234, 64, 85, 37, 81, 229, 122,
    137, 56, 104, 82, 123, 252, 39, 174, 215, 189, 250, 7, 244, 204, 142, 95,
    239, 53, 156, 132, 43, 21, 213, 119, 52, 73, 182, 18, 10, 127, 113, 136,
    253, 157, 24, 65, 125, 147, 216, 88, 44, 206, 254, 36, 175, 222, 184, 54,
    200, 161, 128, 166, 153, 152, 168, 47, 14, 129, 101, 115, 228, 194, 162, 138,
    212, 225, 17, 208, 8, 139, 42, 242, 237, 154, 100, 63, 193, 108, 249, 236,
]
# fmt: on
assert len(_MPBB_CRYPT) == 768, f"mpbbCrypt must be 768 bytes (3x256), got {len(_MPBB_CRYPT)}"
_DECODE_TABLE = bytes(_MPBB_CRYPT[512:768])  # mpbbI - used for decoding (fEncrypt=False)


def decrypt_permute(data: bytes) -> bytes:
    """[MS-PST] 5.1 CryptPermute, decode direction: out[i] = mpbbI[in[i]] for every byte."""
    return data.translate(_DECODE_TABLE)


def decode_data(data: bytes, crypt_method: int) -> bytes:
    if crypt_method == NDB_CRYPT_NONE:
        return data
    if crypt_method == NDB_CRYPT_PERMUTE:
        return decrypt_permute(data)
    raise NotImplementedError(f"Unsupported bCryptMethod {crypt_method:#x} (only NONE/PERMUTE implemented)")


# --- NID (Node ID) - [MS-PST] 2.2.2.1 ---------------------------------------------------
# NID is a 32-bit concept in both formats (Unicode's NBTENTRY/SIENTRY just zero-extend it to 8 bytes
# for field-width alignment) - nid_type()/make_nid() need no ANSI/Unicode distinction.

NID_TYPE_HID = 0x00
NID_TYPE_INTERNAL = 0x01
NID_TYPE_NORMAL_FOLDER = 0x02
NID_TYPE_SEARCH_FOLDER = 0x03
NID_TYPE_NORMAL_MESSAGE = 0x04
NID_TYPE_ATTACHMENT = 0x05
NID_TYPE_ASSOC_MESSAGE = 0x08
NID_TYPE_HIERARCHY_TABLE = 0x0D
NID_TYPE_CONTENTS_TABLE = 0x0E
NID_TYPE_ASSOC_CONTENTS_TABLE = 0x0F
NID_TYPE_ATTACHMENT_TABLE = 0x11
NID_TYPE_RECIPIENT_TABLE = 0x12
NID_TYPE_LTP = 0x1F

# [MS-PST] 2.4.1 Special Internal NIDs
NID_MESSAGE_STORE = 0x21
NID_NAME_TO_ID_MAP = 0x61
NID_ROOT_FOLDER = 0x122


def nid_type(nid: int) -> int:
    return nid & 0x1F


def make_nid(nid_type_: int, nid_index: int) -> int:
    return (nid_index << 5) | nid_type_


# --- BID/IB width helpers - [MS-PST] 2.2.2.2 (BID) / 2.2.2.3 (IB) ------------------------


def _bid_ib_fmt(is_ansi: bool) -> str:
    return "<I" if is_ansi else "<Q"


def _ids_fmt(n: int, is_ansi: bool) -> str:
    """A struct format string for `n` consecutive BID/IB/NID-width fields, e.g. `_ids_fmt(3, True)`
    -> "<III" for an ANSI NBTENTRY's nid+bidData+bidSub."""
    return "<" + ("I" if is_ansi else "Q") * n


def _bid_ib_size(is_ansi: bool) -> int:
    return 4 if is_ansi else 8


def _block_trailer_size(is_ansi: bool) -> int:
    # BLOCKTRAILER ([MS-PST] 2.2.2.8.1): cb(2) + wSig(2) + dwCRC(4) + bid(ANSI 4 / Unicode 8).
    return 12 if is_ansi else 16


def _slblock_entries_off(is_ansi: bool) -> int:
    # SLBLOCK/SIBLOCK header ([MS-PST] 2.2.2.8.3.3.1.1/.2.1): btype(1)+cLevel(1)+cEnt(2) = 4 bytes,
    # then rgentries immediately for ANSI - but Unicode adds a 4-byte dwPadding first (entries at
    # offset 8), to keep the following 8-byte-wide NID/BID fields aligned. ANSI's 4-byte-wide fields
    # are already aligned at offset 4, so it has no padding at all - verified against the real spec
    # (not assumed by analogy with XBLOCK/BTPAGE, which *do* both start entries at a fixed offset 8
    # regardless of format - SLBLOCK/SIBLOCK is the one structure where the entries' start offset
    # itself, not just field width, differs by format).
    return 4 if is_ansi else 8


# --- Header / ROOT - [MS-PST] 2.2.2.6 / 2.2.2.5 -----------------------------------------


@dataclass
class Root:
    ib_file_eof: int
    bref_nbt: tuple  # (bid, ib)
    bref_bbt: tuple


@dataclass
class Header:
    wVer: int
    crypt_method: int
    is_ansi: bool
    root: Root


def parse_header(raw: bytes) -> Header:
    if len(raw) < 4 or raw[0:4] != b"!BDN":
        raise ValueError(f"Not a PST file (bad dwMagic {raw[0:4]!r})")
    if raw[8:10] != b"SM":
        raise ValueError(f"Bad wMagicClient {raw[8:10]!r}")
    wver = struct.unpack_from("<H", raw, 10)[0]
    is_ansi = wver < 23
    if is_ansi and wver not in (14, 15):
        raise NotImplementedError(f"Unrecognized ANSI PST wVer={wver} (only 14/15 are known)")

    if is_ansi:
        # ANSI HEADER: bSentinel/bCryptMethod at offset 460/461 (rgentries(496)+cEnt/cEntMax/cbEnt/
        # cLevel(4) of the header's own leading fields never applies here - this offset comes from
        # the ANSI HEADER field layout itself: dwMagic..dwUnique(36) + rgnid(128) + root(40) +
        # rgbFM(128) + rgbFP(128) = 460). Verified against [MS-PST] 2.2.2.6, not derived by analogy.
        if len(raw) < 512:
            raise ValueError(f"ANSI PST header truncated: expected 512 bytes, got {len(raw)}")
        if raw[460] != 0x80:
            raise ValueError(f"Bad bSentinel {raw[460]:#x} (expected 0x80) - ANSI header offsets may be wrong")
        crypt_method = raw[461]
        root_off = 164
        root = raw[root_off : root_off + 40]
        ib_file_eof = struct.unpack_from("<I", root, 4)[0]
        bref_nbt = struct.unpack_from("<II", root, 20)
        bref_bbt = struct.unpack_from("<II", root, 28)
    else:
        if len(raw) < 564:
            raise ValueError(f"Unicode PST header truncated: expected 564 bytes, got {len(raw)}")
        if raw[512] != 0x80:
            raise ValueError(f"Bad bSentinel {raw[512]:#x} (expected 0x80) - header offsets may be wrong")
        crypt_method = raw[513]
        root_off = 180
        root = raw[root_off : root_off + 72]
        ib_file_eof = struct.unpack_from("<Q", root, 4)[0]
        bref_nbt = struct.unpack_from("<QQ", root, 4 + 8 + 8 + 8 + 8)
        bref_bbt = struct.unpack_from("<QQ", root, 4 + 8 + 8 + 8 + 8 + 16)

    return Header(wVer=wver, crypt_method=crypt_method, is_ansi=is_ansi, root=Root(ib_file_eof, bref_nbt, bref_bbt))


# --- BTree pages - [MS-PST] 2.2.2.7 ------------------------------------------------------


@dataclass
class BTPage:
    ptype: int
    c_level: int
    entries: list  # list of raw per-entry byte slices, length cbEnt each


def read_page(f, ib: int, is_ansi: bool) -> BTPage:
    f.seek(ib)
    raw = f.read(PAGE_SIZE)
    if len(raw) != PAGE_SIZE:
        raise ValueError(f"Short page read at offset {ib:#x}: got {len(raw)} bytes")

    # BTPAGE header fields (cEnt, cEntMax, cbEnt, cLevel) + pageTrailer sit at the very end of the
    # page, but at different offsets for ANSI (rgentries is 496 bytes, no dwPadding) vs Unicode
    # (rgentries is 488 bytes, +4 bytes dwPadding) - [MS-PST] 2.2.2.7.7.1.
    if is_ansi:
        c_ent, cb_ent, c_level = raw[496], raw[498], raw[499]
        trailer_off = 500
    else:
        c_ent, cb_ent, c_level = raw[488], raw[490], raw[491]
        trailer_off = 496

    ptype = raw[trailer_off]
    ptype_repeat = raw[trailer_off + 1]
    if ptype != ptype_repeat:
        raise ValueError(f"Page at {ib:#x}: ptype {ptype:#x} != ptypeRepeat {ptype_repeat:#x}")

    entries = [raw[i * cb_ent : i * cb_ent + cb_ent] for i in range(c_ent)]
    return BTPage(ptype=ptype, c_level=c_level, entries=entries)


def _btentry_bref(entry: bytes, is_ansi: bool) -> tuple:
    # BTENTRY: btkey(ANSI 4 / Unicode 8) + BREF{bid, ib} (ANSI 4+4=8 / Unicode 8+8=16).
    key_size = _bid_ib_size(is_ansi)
    bid, ib = struct.unpack_from(_ids_fmt(2, is_ansi), entry, key_size)
    return bid, ib


def find_nbt_leaf_entry(f, nbt_root_ib: int, nid: int, is_ansi: bool) -> bytes | None:
    """Walk the Node BTree from its root page down to the leaf entry for `nid`, or None."""
    fmt = _bid_ib_fmt(is_ansi)
    ib = nbt_root_ib
    while True:
        page = read_page(f, ib, is_ansi)
        if page.c_level == 0:
            for entry in page.entries:
                entry_nid = struct.unpack_from(fmt, entry, 0)[0]
                if entry_nid == nid:
                    return entry
            return None
        # Intermediate level: descend into the last child whose btkey <= nid.
        chosen = None
        for entry in page.entries:
            btkey = struct.unpack_from(fmt, entry, 0)[0]
            if btkey <= nid:
                chosen = entry
            else:
                break
        if chosen is None:
            return None
        _, child_ib = _btentry_bref(chosen, is_ansi)
        ib = child_ib


def find_bbt_leaf_entry(f, bbt_root_ib: int, bid: int, is_ansi: bool) -> bytes | None:
    """Walk the Block BTree from its root page down to the leaf entry for `bid`, or None."""
    fmt = _bid_ib_fmt(is_ansi)
    lookup_key = bid & ~0x3  # BBT is keyed on the raw BID; low 2 bits (r, i flags) are excluded from comparison
    ib = bbt_root_ib
    while True:
        page = read_page(f, ib, is_ansi)
        if page.c_level == 0:
            for entry in page.entries:
                entry_bid = struct.unpack_from(fmt, entry, 0)[0]
                if (entry_bid & ~0x3) == lookup_key:
                    return entry
            return None
        chosen = None
        for entry in page.entries:
            btkey = struct.unpack_from(fmt, entry, 0)[0]
            if (btkey & ~0x3) <= lookup_key:
                chosen = entry
            else:
                break
        if chosen is None:
            return None
        _, child_ib = _btentry_bref(chosen, is_ansi)
        ib = child_ib


def _read_bbt_block(f, bbt_root_ib: int, bid: int, is_ansi: bool) -> tuple:
    """Resolve a BID via the BBT and read its raw (still block-trailer-stripped, still
    permutation-encoded) bytes off disk. Returns (blockBid, data) - `blockBid` carries the `i`
    (internal/XBLOCK) flag callers need; shared by every caller that would otherwise repeat the
    BBTENTRY-parse-then-seek-then-round-up-to-64 dance (read_block_parts, XBLOCK/XXBLOCK chain
    traversal, and both subnode-BTree readers)."""
    entry = find_bbt_leaf_entry(f, bbt_root_ib, bid, is_ansi)
    if entry is None:
        raise KeyError(f"BID {bid:#x} not found in Block BTree")
    # BBTENTRY: BREF{bid, ib} (ANSI 8 / Unicode 16) + cb(2) + cRef(2) [+ dwPadding(4), Unicode only].
    bref_size = _bid_ib_size(is_ansi) * 2
    block_bid, block_ib = struct.unpack_from(_ids_fmt(2, is_ansi), entry, 0)
    cb = struct.unpack_from("<H", entry, bref_size)[0]

    block_size = cb + _block_trailer_size(is_ansi)
    block_size += (-block_size) % 64  # round up to 64-byte boundary
    f.seek(block_ib)
    data = f.read(block_size)[:cb]
    return block_bid, data


def read_block_parts(f, bbt_root_ib: int, bid: int, crypt_method: int, is_ansi: bool) -> list:
    """Resolve a BID to its data block's decoded bytes as a list of leaf-block chunks.

    A plain (non-internal) block yields a single-element list. An XBLOCK/XXBLOCK chain yields one
    element per leaf data block, *not* concatenated - callers that need row/record-aligned data
    (e.g. a TC Row Matrix, see ltp.py) must not simply join these, since each underlying NDB block
    is only ~8KB and reserves any leftover space at its end as padding rather than starting the
    next record there; joining raw would splice that padding into the middle of the byte stream.
    `read_block_raw` (whole-blob callers, where padding is never present) does the joining itself.
    """
    block_bid, data = _read_bbt_block(f, bbt_root_ib, bid, is_ansi)
    is_internal = bool(block_bid & 0x2)
    if is_internal:
        return _read_xblock_parts(f, bbt_root_ib, data, crypt_method, is_ansi)
    return [decode_data(data, crypt_method)]


def read_block_raw(f, bbt_root_ib: int, bid: int, crypt_method: int, is_ansi: bool) -> bytes:
    """Resolve a BID to its data block's decoded bytes, concatenated (following XBLOCK/XXBLOCK chains)."""
    return b"".join(read_block_parts(f, bbt_root_ib, bid, crypt_method, is_ansi))


def _read_xblock_parts(f, bbt_root_ib: int, data: bytes, crypt_method: int, is_ansi: bool) -> list:
    # XBLOCK/XXBLOCK header: btype(1) + cLevel(1) + cEnt(2) + lcbTotal(4) - fixed 8 bytes in both
    # formats (lcbTotal never widens) - then cEnt BIDs, each ANSI 4 / Unicode 8 bytes.
    btype, c_level, c_ent = data[0], data[1], struct.unpack_from("<H", data, 2)[0]
    if btype != 0x01:
        raise ValueError(f"Expected XBLOCK/XXBLOCK btype 0x01, got {btype:#x}")
    fmt = _bid_ib_fmt(is_ansi)
    bid_size = _bid_ib_size(is_ansi)
    bids = [struct.unpack_from(fmt, data, 8 + i * bid_size)[0] for i in range(c_ent)]
    parts = []
    if c_level == 1:
        for bid in bids:
            parts.extend(read_block_parts(f, bbt_root_ib, bid, crypt_method, is_ansi))
    elif c_level == 2:
        for bid in bids:
            parts.extend(_read_xblock_bid_parts(f, bbt_root_ib, bid, crypt_method, is_ansi))
    else:
        raise ValueError(f"Unexpected XBLOCK cLevel {c_level}")
    return parts


def _read_xblock_bid_parts(f, bbt_root_ib: int, bid: int, crypt_method: int, is_ansi: bool) -> list:
    _block_bid, data = _read_bbt_block(f, bbt_root_ib, bid, is_ansi)
    return _read_xblock_parts(f, bbt_root_ib, data, crypt_method, is_ansi)


# --- Subnode BTree - [MS-PST] 2.2.2.8.3.3 ------------------------------------------------


def find_subnode(f, bbt_root_ib: int, sub_bid: int, crypt_method: int, target_nid: int, is_ansi: bool):
    """Look up `target_nid` in the subnode BTree rooted at `sub_bid`. Returns (bidData, bidSub) or None.

    Subnode BTree blocks are structural (SLBLOCK/SIBLOCK), not "data" blocks, so - like BTree
    pages - they are NOT permutation-encoded, only referenced via the BBT for their raw bytes.
    """
    _block_bid, data = _read_bbt_block(f, bbt_root_ib, sub_bid, is_ansi)

    btype, c_level, c_ent = data[0], data[1], struct.unpack_from("<H", data, 2)[0]
    if btype != 0x02:
        raise ValueError(f"Expected SLBLOCK/SIBLOCK btype 0x02, got {btype:#x}")
    id_size = _bid_ib_size(is_ansi)
    entries_off = _slblock_entries_off(is_ansi)

    if c_level == 0:
        # SLBLOCK: cEnt x SLENTRY{nid, bidData, bidSub} (each field ANSI 4 / Unicode 8).
        entry_size = id_size * 3
        for i in range(c_ent):
            off = entries_off + i * entry_size
            entry_nid, bid_data, bid_sub = struct.unpack_from(_ids_fmt(3, is_ansi), data, off)
            if (entry_nid & 0xFFFFFFFF) == target_nid:
                return bid_data, bid_sub
        return None

    # SIBLOCK (cLevel == 1): cEnt x SIENTRY{nid, bid} (each field ANSI 4 / Unicode 8), pointing at
    # child SLBLOCKs.
    entry_size = id_size * 2
    chosen_bid = None
    for i in range(c_ent):
        off = entries_off + i * entry_size
        entry_nid, child_bid = struct.unpack_from(_ids_fmt(2, is_ansi), data, off)
        if (entry_nid & 0xFFFFFFFF) <= target_nid:
            chosen_bid = child_bid
        else:
            break
    if chosen_bid is None:
        return None
    return find_subnode(f, bbt_root_ib, chosen_bid, crypt_method, target_nid, is_ansi)


def list_subnode_entries(f, bbt_root_ib: int, sub_bid: int, is_ansi: bool) -> list:
    """Return every (nid, bidData, bidSub) entry in the subnode BTree rooted at `sub_bid`.

    Unlike a folder's Hierarchy/Contents Table NID (built from the folder's own NID index via
    make_nid), a message's per-object subnodes - its Recipient Table, Attachment Table, and each
    individual attachment - use NIDs assigned independently by the writer with no relationship to
    the parent message's own NID (verified against data/personal-email-backup.pst: a message with
    NID 0x200044 had its Recipient/Attachment Tables at subnode NIDs 0x692/0x671). So finding them
    requires enumerating every subnode and matching by `nid_type()`, not deriving the NID directly.
    """
    _block_bid, data = _read_bbt_block(f, bbt_root_ib, sub_bid, is_ansi)

    btype, c_level, c_ent = data[0], data[1], struct.unpack_from("<H", data, 2)[0]
    if btype != 0x02:
        raise ValueError(f"Expected SLBLOCK/SIBLOCK btype 0x02, got {btype:#x}")
    id_size = _bid_ib_size(is_ansi)
    entries_off = _slblock_entries_off(is_ansi)

    if c_level == 0:
        entry_size = id_size * 3
        entries = []
        for i in range(c_ent):
            off = entries_off + i * entry_size
            entry_nid, bid_data, bid_sub = struct.unpack_from(_ids_fmt(3, is_ansi), data, off)
            entries.append((entry_nid & 0xFFFFFFFF, bid_data, bid_sub))
        return entries

    # SIBLOCK (cLevel == 1): recurse into every child SLBLOCK, not just one.
    entry_size = id_size * 2
    entries = []
    for i in range(c_ent):
        off = entries_off + i * entry_size
        _entry_nid, child_bid = struct.unpack_from(_ids_fmt(2, is_ansi), data, off)
        entries.extend(list_subnode_entries(f, bbt_root_ib, child_bid, is_ansi))
    return entries


class PSTFile:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._f = open(self.path, "rb")  # noqa: SIM115 - lives for the object's lifetime, closed in close()/__exit__
        header_bytes = self._f.read(HEADER_READ_SIZE)
        self.header = parse_header(header_bytes)

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> "PSTFile":  # noqa: PYI034 - typing.Self needs Python 3.11+, project supports 3.10+
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def resolve_nid(self, nid: int):
        """Return (bidData, bidSub) for a top-level NID via the Node BTree, or None."""
        entry = find_nbt_leaf_entry(self._f, self.header.root.bref_nbt[1], nid, self.header.is_ansi)
        if entry is None:
            return None
        # NBTENTRY: nid + bidData + bidSub (each ANSI 4 / Unicode 8) + nidParent(4) [+ dwPadding(4), Unicode only].
        _, bid_data, bid_sub = struct.unpack_from(_ids_fmt(3, self.header.is_ansi), entry, 0)
        return bid_data, bid_sub

    def read_block(self, bid: int) -> bytes:
        return read_block_raw(self._f, self.header.root.bref_bbt[1], bid, self.header.crypt_method, self.header.is_ansi)

    def read_block_parts(self, bid: int) -> list:
        return read_block_parts(self._f, self.header.root.bref_bbt[1], bid, self.header.crypt_method, self.header.is_ansi)

    def read_subnode(self, sub_bid: int, nid: int):
        return find_subnode(self._f, self.header.root.bref_bbt[1], sub_bid, self.header.crypt_method, nid, self.header.is_ansi)

    def list_subnodes(self, sub_bid: int) -> list:
        return list_subnode_entries(self._f, self.header.root.bref_bbt[1], sub_bid, self.header.is_ansi)
