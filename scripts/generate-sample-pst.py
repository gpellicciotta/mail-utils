import struct
from pathlib import Path

from mail_utils.outlook.messages import fetch_message, parse_message
from mail_utils.outlook.ndb import (
    NID_TYPE_CONTENTS_TABLE,
    NID_TYPE_HIERARCHY_TABLE,
    PTYPE_BBT,
    PTYPE_NBT,
    PSTFile,
    make_nid,
)
from mail_utils.outlook.tree import walk_folders

PROP_DISPLAY_NAME = 0x3001
PROP_LTP_ROW_ID = 0x67F2
PROP_SUBJECT = 0x0037
PROP_BODY = 0x1000
PROP_SENDER_NAME = 0x0C1A
PROP_SENDER_SMTP_ADDRESS = 0x5D01
PROP_CLIENT_SUBMIT_TIME = 0x0039
PROP_INTERNET_MESSAGE_ID = 0x1035

PTYP_STRING = 0x001F
PTYP_INTEGER32 = 0x0003
PTYP_TIME = 0x0040


def make_heap(client_sig: int, user_root_data: bytes, extra_allocs: list[bytes]) -> bytes:
    allocs = [user_root_data] + extra_allocs
    offset = 8
    rgib = [offset]
    body = bytearray()
    for a in allocs:
        if len(a) % 2 != 0:
            a = a + b"\x00"
        body.extend(a)
        offset += len(a)
        rgib.append(offset)

    c_alloc = len(allocs)
    pagemap = struct.pack("<HH", c_alloc, 0) + b"".join(struct.pack("<H", o) for o in rgib)
    ib_hnpm = offset
    hdr = struct.pack("<HBB I", ib_hnpm, 0xEC, client_sig, 0x00000020)
    block = hdr + body + pagemap
    return bytes(block)


def make_bth_pc(props: list[tuple[int, int, bytes]]) -> bytes:
    # Build PC BTH and Heap
    # user_root is BTHHEADER: bType(0xB5), cbKey(2), cbEnt(6), bIdxLevels(0), hidRoot(0x00000040)
    extra_allocs = []
    bth_entries = bytearray()
    for prop_id, prop_type, val_bytes in props:
        if len(val_bytes) <= 4 and prop_type != PTYP_STRING:
            padded_val = val_bytes.ljust(4, b"\x00")
            bth_entries.extend(struct.pack("<HH4s", prop_id, prop_type, padded_val))
        else:
            # allocate in heap
            extra_allocs.append(val_bytes)
            # HID is: ((index + 3) << 5) since Alloc 0 = header, Alloc 1 = BTH root entries
            hid = (len(extra_allocs) + 2) << 5
            bth_entries.extend(struct.pack("<HHI", prop_id, prop_type, hid))

    bth_root_alloc = bytes(bth_entries)
    # user root header
    bth_header = struct.pack("<BBBB I", 0xB5, 2, 6, 0, 0x00000040)
    all_allocs = [bth_root_alloc] + extra_allocs
    return make_heap(0xBC, bth_header, all_allocs)


def make_tc(columns: list[tuple[int, int]], rows: list[list[bytes]]) -> bytes:
    # Table Context Heap
    # User root is TCINFO
    c_cols = len(columns)
    col_defs = []
    ib_cur = 0
    for i, (prop_id, prop_type) in enumerate(columns):
        tag = (prop_id << 16) | prop_type
        cb_data = 4
        col_defs.append((tag, ib_cur, cb_data, i))
        ib_cur += cb_data
    row_width = ib_cur

    # Build row matrix
    row_matrix = bytearray()
    extra_allocs = []
    for row_cells in rows:
        row_bytes = bytearray()
        for i, val in enumerate(row_cells):
            prop_type = columns[i][1]
            if len(val) <= 4 and prop_type != PTYP_STRING:
                row_bytes.extend(val.ljust(4, b"\x00"))
            else:
                extra_allocs.append(val)
                hid = (len(extra_allocs) + 2) << 5
                row_bytes.extend(struct.pack("<I", hid))
        row_matrix.extend(row_bytes)

    # Alloc 1: Row matrix (HID 0x00000040)
    all_allocs = [bytes(row_matrix)] + extra_allocs
    hnid_rows = 0x00000040

    # TCINFO: bType(0x7C), cCols(1 byte), rgib(4 * uint16: rgib[3]=row_width), hidRowIndex(uint32), hnidRows(uint32), hidIndex(uint32)
    tcinfo = bytearray(struct.pack("<BB4H III", 0x7C, c_cols, 0, 0, 0, row_width, 0, hnid_rows, 0))
    for tag, ib_data, cb_data, i_bit in col_defs:
        tcinfo.extend(struct.pack("<IHBB", tag, ib_data, cb_data, i_bit))

    return make_heap(0x7C, bytes(tcinfo), all_allocs)


def generate_sample_pst(target_path: Path):
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Root folder PC
    root_pc = make_bth_pc([(PROP_DISPLAY_NAME, PTYP_STRING, "Top of Outlook data file".encode("utf-16-le"))])

    # 2. Root folder Hierarchy Table (contains 1 child folder: "Inbox", NID 0x202)
    root_hierarchy = make_tc(
        [(PROP_LTP_ROW_ID, PTYP_INTEGER32), (PROP_DISPLAY_NAME, PTYP_STRING)],
        [[struct.pack("<I", 0x202), "Inbox".encode("utf-16-le")]],
    )

    # 3. Root folder Contents Table (empty)
    root_contents = make_tc([(PROP_LTP_ROW_ID, PTYP_INTEGER32)], [])

    # 4. Inbox folder PC
    inbox_pc = make_bth_pc([(PROP_DISPLAY_NAME, PTYP_STRING, "Inbox".encode("utf-16-le"))])

    # 5. Inbox folder Contents Table (contains 2 messages: NID 0x304 and 0x324)
    inbox_contents = make_tc([(PROP_LTP_ROW_ID, PTYP_INTEGER32)], [[struct.pack("<I", 0x304)], [struct.pack("<I", 0x324)]])

    # 6. Message 1 PC (0x304)
    msg1_pc = make_bth_pc(
        [
            (PROP_INTERNET_MESSAGE_ID, PTYP_STRING, "<sample-pst-1@example.com>".encode("utf-16-le")),
            (PROP_SUBJECT, PTYP_STRING, "Welcome to Outlook".encode("utf-16-le")),
            (PROP_SENDER_NAME, PTYP_STRING, "Alice Smith".encode("utf-16-le")),
            (PROP_SENDER_SMTP_ADDRESS, PTYP_STRING, "alice@example.com".encode("utf-16-le")),
            (PROP_BODY, PTYP_STRING, "Hello and welcome to your new Outlook mailbox!".encode("utf-16-le")),
            (PROP_CLIENT_SUBMIT_TIME, PTYP_TIME, struct.pack("<Q", 134117424000000000)),
        ]
    )

    # 7. Message 2 PC (0x324)
    msg2_pc = make_bth_pc(
        [
            (PROP_INTERNET_MESSAGE_ID, PTYP_STRING, "<sample-pst-2@example.com>".encode("utf-16-le")),
            (PROP_SUBJECT, PTYP_STRING, "Project Quarterly Update".encode("utf-16-le")),
            (PROP_SENDER_NAME, PTYP_STRING, "Bob Jones".encode("utf-16-le")),
            (PROP_SENDER_SMTP_ADDRESS, PTYP_STRING, "bob@example.com".encode("utf-16-le")),
            (PROP_BODY, PTYP_STRING, "The project is on track and all milestones are met.".encode("utf-16-le")),
            (PROP_CLIENT_SUBMIT_TIME, PTYP_TIME, struct.pack("<Q", 134118288000000000)),
        ]
    )

    blocks = [
        (0x20, root_pc),
        (0x30, root_hierarchy),
        (0x40, root_contents),
        (0x50, inbox_pc),
        (0x60, inbox_contents),
        (0x70, msg1_pc),
        (0x80, msg2_pc),
    ]

    # Layout file:
    # 0..1024: Header (564 bytes padded to 1024)
    # 1024..1536: NBT Page (ptype 0x81)
    # 1536..2048: BBT Page (ptype 0x80)
    # 2048..: Data Blocks
    offset = 2048
    bbt_entries = []
    block_data_bytes = bytearray()
    for bid, b_data in blocks:
        cb = len(b_data)
        block_size = cb + 16
        block_size += (-block_size) % 64
        trailer = struct.pack("<HHII", 0, 0, 0, bid)
        full_block = b_data + b"\x00" * (block_size - 16 - cb) + trailer
        bbt_entries.append((bid, offset, cb))
        block_data_bytes.extend(full_block)
        offset += len(full_block)

    total_eof = offset

    # NBT entries: (nid, bidData, bidSub, nidParent)
    nbt_records = [
        (0x21, 0, 0, 0),  # NID_MESSAGE_STORE
        (0x122, 0x20, 0, 0),  # NID_ROOT_FOLDER
        (make_nid(NID_TYPE_HIERARCHY_TABLE, 0x122 >> 5), 0x30, 0, 0x122),
        (make_nid(NID_TYPE_CONTENTS_TABLE, 0x122 >> 5), 0x40, 0, 0x122),
        (0x202, 0x50, 0, 0x122),  # Inbox folder
        (make_nid(NID_TYPE_CONTENTS_TABLE, 0x202 >> 5), 0x60, 0, 0x202),
        (0x304, 0x70, 0, 0x202),  # Msg 1
        (0x324, 0x80, 0, 0x202),  # Msg 2
    ]

    # Build NBT page at 1024
    nbt_page_bytes = bytearray(512)
    for i, (nid, bid_data, bid_sub, nid_parent) in enumerate(nbt_records):
        struct.pack_into("<QQQQ", nbt_page_bytes, i * 32, nid, bid_data, bid_sub, nid_parent)
    # Page header & trailer
    # cEnt(488), cEntMax(489), cbEnt(490), cLevel(491)
    struct.pack_into("<BBBB", nbt_page_bytes, 488, len(nbt_records), 15, 32, 0)
    # trailer: ptype(496)=0x81, ptypeRepeat(497)=0x81, wSig(498)=0, dwCRC(500)=0, bid(504)=1
    struct.pack_into("<BBHIQ", nbt_page_bytes, 496, PTYPE_NBT, PTYPE_NBT, 0, 0, 1)

    # Build BBT page at 1536
    bbt_page_bytes = bytearray(512)
    for i, (bid, ib, cb) in enumerate(bbt_entries):
        struct.pack_into("<QQHH I", bbt_page_bytes, i * 24, bid, ib, cb, 1, 0)
    struct.pack_into("<BBBB", bbt_page_bytes, 488, len(bbt_entries), 20, 24, 0)
    struct.pack_into("<BBHIQ", bbt_page_bytes, 496, PTYPE_BBT, PTYPE_BBT, 0, 0, 2)

    # Build Header at 0 (1024 bytes)
    hdr = bytearray(1024)
    hdr[0:4] = b"!BDN"
    hdr[8:10] = b"SM"
    struct.pack_into("<H", hdr, 10, 23)  # wVer
    struct.pack_into("<H", hdr, 12, 19)  # wVerClient
    hdr[512] = 0x80  # bSentinel
    hdr[513] = 0x00  # bCryptMethod = NDB_CRYPT_NONE

    # ROOT struct at offset 180 (72 bytes):
    # ibFileEOF(4)=total_eof, brefNBT(4+32)=(1, 1024), brefBBT(4+48)=(2, 1536)
    struct.pack_into("<Q", hdr, 180 + 4, total_eof)
    struct.pack_into("<QQ", hdr, 180 + 36, 1, 1024)
    struct.pack_into("<QQ", hdr, 180 + 52, 2, 1536)

    full_pst = bytes(hdr) + bytes(nbt_page_bytes) + bytes(bbt_page_bytes) + bytes(block_data_bytes)
    target_path.write_bytes(full_pst)
    print("Generated sample PST:", target_path, len(full_pst), "bytes")


if __name__ == "__main__":
    out = Path("tests/fixtures/sample.pst")
    generate_sample_pst(out)
    with PSTFile(out) as pst:
        folders = walk_folders(pst)
        print("Walked folders:", [f.path for f in folders])
        for f in folders:
            print(f"  Folder: {f.path!r} -> {len(f.message_nids)} messages")
            for nid in f.message_nids:
                raw = fetch_message(pst, nid)
                msg = parse_message(raw)
                print("    Msg:", msg["id"], msg["sender"], msg["subject"])
