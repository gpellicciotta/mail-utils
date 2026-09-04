import io
import struct

import pytest

from mail_utils.outlook.ndb import (
    HEADER_READ_SIZE,
    NDB_CRYPT_NONE,
    NDB_CRYPT_PERMUTE,
    decode_data,
    decrypt_permute,
    find_bbt_leaf_entry,
    find_nbt_leaf_entry,
    find_subnode,
    list_subnode_entries,
    make_nid,
    nid_type,
    parse_header,
    read_block_raw,
)


def test_decrypt_permute_decode_table_is_a_bijection():
    # A mistranscribed lookup table would almost certainly not be a valid permutation of 0-255 -
    # this is a cheap structural sanity check on _MPBB_CRYPT independent of any real PST file.
    decoded = decrypt_permute(bytes(range(256)))
    assert sorted(decoded) == list(range(256))


def test_decrypt_permute_round_trips_through_the_spec_encode_table():
    # [MS-PST] 5.1: mpbbR (encode) and mpbbI (decode) are meant to be inverses of each other -
    # encoding then decoding every byte value should return the identity.
    from mail_utils.outlook.ndb import _MPBB_CRYPT

    encode_table = bytes(_MPBB_CRYPT[0:256])
    encoded = bytes(range(256)).translate(encode_table)
    assert decrypt_permute(encoded) == bytes(range(256))


def test_decode_data_none_is_passthrough():
    assert decode_data(b"abc", NDB_CRYPT_NONE) == b"abc"


def test_decode_data_rejects_unsupported_crypt_method():
    with pytest.raises(NotImplementedError):
        decode_data(b"abc", 0x02)  # NDB_CRYPT_CYCLIC - deliberately unimplemented


def test_decode_data_permute_is_reversible_via_encode_table():
    from mail_utils.outlook.ndb import _MPBB_CRYPT

    encode_table = bytes(_MPBB_CRYPT[0:256])
    original = b"hello pst"
    encoded = original.translate(encode_table)
    assert decode_data(encoded, NDB_CRYPT_PERMUTE) == original


def test_nid_type_and_make_nid_round_trip():
    for type_, index in [(0x00, 0), (0x02, 1), (0x0E, 12345), (0x1F, 0x7FFFFFF)]:
        nid = make_nid(type_, index)
        assert nid_type(nid) == type_


def test_parse_header_rejects_bad_magic():
    raw = bytearray(HEADER_READ_SIZE)
    raw[0:4] = b"XXXX"
    with pytest.raises(ValueError, match="Not a PST file"):
        parse_header(bytes(raw))


def test_parse_header_rejects_short_input():
    with pytest.raises(ValueError, match="Not a PST file"):
        parse_header(b"too short")


def test_parse_header_rejects_short_unicode_input():
    raw = bytearray(600)
    raw[0:4] = b"!BDN"
    raw[8:10] = b"SM"
    raw[10:12] = (23).to_bytes(2, "little")
    with pytest.raises(ValueError, match="truncated"):
        parse_header(bytes(raw[:500]))


# --- ANSI format ([MS-PST] 2.2.2.6/2.2.2.5 - see ndb.py's module docstring for how these exact
# offsets were verified against the real spec) -----------------------------------------------

_ANSI_ROOT_OFF = 164


def _make_ansi_header(wver=15, crypt_method=NDB_CRYPT_NONE, ib_file_eof=0x1000, bref_nbt=(0x20, 0x800), bref_bbt=(0x24, 0xC00)):
    raw = bytearray(HEADER_READ_SIZE)
    raw[0:4] = b"!BDN"
    raw[8:10] = b"SM"
    raw[10:12] = wver.to_bytes(2, "little")
    raw[460] = 0x80  # bSentinel
    raw[461] = crypt_method
    raw[_ANSI_ROOT_OFF + 4 : _ANSI_ROOT_OFF + 8] = ib_file_eof.to_bytes(4, "little")
    raw[_ANSI_ROOT_OFF + 20 : _ANSI_ROOT_OFF + 24] = bref_nbt[0].to_bytes(4, "little")
    raw[_ANSI_ROOT_OFF + 24 : _ANSI_ROOT_OFF + 28] = bref_nbt[1].to_bytes(4, "little")
    raw[_ANSI_ROOT_OFF + 28 : _ANSI_ROOT_OFF + 32] = bref_bbt[0].to_bytes(4, "little")
    raw[_ANSI_ROOT_OFF + 32 : _ANSI_ROOT_OFF + 36] = bref_bbt[1].to_bytes(4, "little")
    return bytes(raw)


@pytest.mark.parametrize("wver", [14, 15])
def test_parse_header_accepts_ansi_wver(wver):
    header = parse_header(_make_ansi_header(wver=wver))
    assert header.is_ansi is True
    assert header.wVer == wver


def test_parse_header_ansi_reads_root_fields():
    header = parse_header(_make_ansi_header(ib_file_eof=0x12345, bref_nbt=(0x20, 0x800), bref_bbt=(0x24, 0xC00)))
    assert header.root.ib_file_eof == 0x12345
    assert header.root.bref_nbt == (0x20, 0x800)
    assert header.root.bref_bbt == (0x24, 0xC00)


def test_parse_header_ansi_reads_crypt_method():
    header = parse_header(_make_ansi_header(crypt_method=NDB_CRYPT_PERMUTE))
    assert header.crypt_method == NDB_CRYPT_PERMUTE


def test_parse_header_rejects_unrecognized_ansi_wver():
    with pytest.raises(NotImplementedError, match="ANSI"):
        parse_header(_make_ansi_header(wver=16))


def test_parse_header_rejects_bad_ansi_sentinel():
    raw = bytearray(_make_ansi_header())
    raw[460] = 0x00
    with pytest.raises(ValueError, match="bSentinel"):
        parse_header(bytes(raw))


def test_parse_header_unicode_still_works_unchanged():
    # Regression guard: the existing Unicode header layout/offsets must be untouched by adding ANSI.
    raw = bytearray(HEADER_READ_SIZE)
    raw[0:4] = b"!BDN"
    raw[8:10] = b"SM"
    raw[10:12] = (23).to_bytes(2, "little")
    raw[512] = 0x80  # bSentinel
    raw[513] = NDB_CRYPT_NONE
    root_off = 180
    raw[root_off + 4 : root_off + 12] = (0x9999).to_bytes(8, "little")  # ibFileEof
    raw[root_off + 36 : root_off + 44] = (0x30).to_bytes(8, "little")  # BREFNBT.bid
    raw[root_off + 44 : root_off + 52] = (0x1000).to_bytes(8, "little")  # BREFNBT.ib
    raw[root_off + 52 : root_off + 60] = (0x34).to_bytes(8, "little")  # BREFBBT.bid
    raw[root_off + 60 : root_off + 68] = (0x1800).to_bytes(8, "little")  # BREFBBT.ib
    header = parse_header(bytes(raw))
    assert header.is_ansi is False
    assert header.root.ib_file_eof == 0x9999
    assert header.root.bref_nbt == (0x30, 0x1000)
    assert header.root.bref_bbt == (0x34, 0x1800)


# --- BTree pages / entries, ANSI (32-bit) widths ----------------------------------------------


def _make_ansi_btpage(entries: bytes, cb_ent: int, c_level: int, ptype: int) -> bytes:
    page = bytearray(512)
    page[0 : len(entries)] = entries
    page[496] = len(entries) // cb_ent  # cEnt
    page[497] = 0  # cEntMax (unused by reader)
    page[498] = cb_ent
    page[499] = c_level
    page[500] = ptype
    page[501] = ptype  # ptypeRepeat
    return bytes(page)


def test_read_page_ansi_nbt_leaf():
    # Two NBTENTRYs (16 bytes each, ANSI): nid(4) + bidData(4) + bidSub(4) + nidParent(4).
    entries = struct.pack("<IIII", 0x100, 0x40, 0x0, 0x0) + struct.pack("<IIII", 0x200, 0x44, 0x48, 0x0)
    page_bytes = _make_ansi_btpage(entries, cb_ent=16, c_level=0, ptype=0x81)  # PTYPE_NBT
    f = io.BytesIO(page_bytes)
    entry = find_nbt_leaf_entry(f, 0, 0x200, is_ansi=True)
    assert entry is not None
    nid, bid_data, bid_sub, _nid_parent = struct.unpack_from("<IIII", entry, 0)
    assert (nid, bid_data, bid_sub) == (0x200, 0x44, 0x48)


def test_read_page_ansi_bbt_leaf():
    # One BBTENTRY (12 bytes, ANSI): BREF{bid(4), ib(4)} + cb(2) + cRef(2).
    entries = struct.pack("<IIHH", 0x84, 0x900, 128, 1)
    page_bytes = _make_ansi_btpage(entries, cb_ent=12, c_level=0, ptype=0x80)  # PTYPE_BBT
    f = io.BytesIO(page_bytes)
    entry = find_bbt_leaf_entry(f, 0, 0x84, is_ansi=True)
    assert entry is not None
    bid, ib, cb, cref = struct.unpack_from("<IIHH", entry, 0)
    assert (bid, ib, cb, cref) == (0x84, 0x900, 128, 1)


def test_read_page_ansi_intermediate_descends_via_btentry():
    # Root (cLevel=1) has one BTENTRY (12 bytes, ANSI: btkey(4) + BREF{bid(4), ib(4)}) pointing at a
    # leaf page holding the real NBTENTRY - exercises _btentry_bref's ANSI width.
    leaf_entries = struct.pack("<IIII", 0x300, 0x50, 0x0, 0x0)
    leaf_page = _make_ansi_btpage(leaf_entries, cb_ent=16, c_level=0, ptype=0x81)
    root_entry = struct.pack("<III", 0x0, 0x0, 512)  # btkey=0, BREF{bid=0, ib=512 (leaf page offset)}
    root_page = _make_ansi_btpage(root_entry, cb_ent=12, c_level=1, ptype=0x81)
    f = io.BytesIO(root_page + leaf_page)
    entry = find_nbt_leaf_entry(f, 0, 0x300, is_ansi=True)
    assert entry is not None
    nid = struct.unpack_from("<I", entry, 0)[0]
    assert nid == 0x300


def test_read_block_raw_ansi_plain_block():
    # BBT root page (leaf) with one BBTENTRY pointing at a plain (non-internal, low bit of bid clear)
    # data block at a 64-byte-aligned offset after the page.
    block_data = b"hello ansi block"
    trailer = bytes(12)  # BLOCKTRAILER content is irrelevant here, only its size (ANSI: 12) matters
    block_size = len(block_data) + len(trailer)
    block_size += (-block_size) % 64
    block_bytes = (block_data + trailer).ljust(block_size, b"\x00")
    bbt_entry = struct.pack("<IIHH", 0x08, 512, len(block_data), 1)  # bid low bits clear => not internal
    bbt_page = _make_ansi_btpage(bbt_entry, cb_ent=12, c_level=0, ptype=0x80)
    f = io.BytesIO(bbt_page + block_bytes)
    result = read_block_raw(f, 0, 0x08, NDB_CRYPT_NONE, is_ansi=True)
    assert result == block_data


def test_subnode_btree_ansi_slblock():
    # SLBLOCK (btype=2, cLevel=0) with one SLENTRY (12 bytes, ANSI: nid(4)+bidData(4)+bidSub(4)).
    # ANSI header is just btype(1)+cLevel(1)+cEnt(2) = 4 bytes - no padding (unlike Unicode's 8,
    # since ANSI's 4-byte-wide entries are already aligned at offset 4).
    slblock_body = struct.pack("<BBH", 0x02, 0x00, 1) + struct.pack("<III", 0x77, 0x88, 0x0)
    trailer = bytes(12)
    block_size = len(slblock_body) + len(trailer)
    block_size += (-block_size) % 64
    slblock_bytes = (slblock_body + trailer).ljust(block_size, b"\x00")
    bbt_entry = struct.pack("<IIHH", 0x10, 512, len(slblock_body), 1)
    bbt_page = _make_ansi_btpage(bbt_entry, cb_ent=12, c_level=0, ptype=0x80)
    f = io.BytesIO(bbt_page + slblock_bytes)

    result = find_subnode(f, 0, 0x10, NDB_CRYPT_NONE, target_nid=0x77, is_ansi=True)
    assert result == (0x88, 0x0)

    entries = list_subnode_entries(f, 0, 0x10, is_ansi=True)
    assert entries == [(0x77, 0x88, 0x0)]


def test_subnode_btree_ansi_siblock_descends_to_slblock():
    # SIBLOCK (btype=2, cLevel=1) with one SIENTRY (8 bytes, ANSI: nid(4)+bid(4)) pointing at a
    # child SLBLOCK - exercises the recursive intermediate-level path with the same ANSI
    # no-padding-before-entries layout as the leaf case above.
    slblock_body = struct.pack("<BBH", 0x02, 0x00, 1) + struct.pack("<III", 0x77, 0x88, 0x0)
    slblock_trailer_size = 12
    slblock_size = len(slblock_body) + slblock_trailer_size
    slblock_size += (-slblock_size) % 64
    slblock_bytes = slblock_body.ljust(slblock_size, b"\x00")

    siblock_body = struct.pack("<BBH", 0x02, 0x01, 1) + struct.pack("<II", 0x77, 0x20)  # SIENTRY{nid, bid}
    siblock_size = len(siblock_body) + slblock_trailer_size
    siblock_size += (-siblock_size) % 64
    siblock_bytes = siblock_body.ljust(siblock_size, b"\x00")

    bbt_entries = struct.pack("<IIHH", 0x10, 512, len(siblock_body), 1) + struct.pack(
        "<IIHH", 0x20, 512 + siblock_size, len(slblock_body), 1
    )
    bbt_page = _make_ansi_btpage(bbt_entries, cb_ent=12, c_level=0, ptype=0x80)
    f = io.BytesIO(bbt_page + siblock_bytes + slblock_bytes)

    result = find_subnode(f, 0, 0x10, NDB_CRYPT_NONE, target_nid=0x77, is_ansi=True)
    assert result == (0x88, 0x0)

    entries = list_subnode_entries(f, 0, 0x10, is_ansi=True)
    assert entries == [(0x77, 0x88, 0x0)]
