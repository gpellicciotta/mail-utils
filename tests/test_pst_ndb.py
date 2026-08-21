import pytest

from mail_utils.outlook.ndb import (
    HEADER_SIZE,
    NDB_CRYPT_NONE,
    NDB_CRYPT_PERMUTE,
    decode_data,
    decrypt_permute,
    make_nid,
    nid_type,
    parse_header,
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
    raw = bytearray(HEADER_SIZE)
    raw[0:4] = b"XXXX"
    with pytest.raises(ValueError, match="Not a PST file"):
        parse_header(bytes(raw))


def test_parse_header_rejects_ansi_format():
    raw = bytearray(HEADER_SIZE)
    raw[0:4] = b"!BDN"
    raw[8:10] = b"SM"
    raw[10:12] = (14).to_bytes(2, "little")  # wVer < 23 => ANSI (32-bit) format
    with pytest.raises(NotImplementedError, match="ANSI"):
        parse_header(bytes(raw))


def test_parse_header_rejects_short_input():
    with pytest.raises(ValueError, match="truncated"):
        parse_header(b"too short")
