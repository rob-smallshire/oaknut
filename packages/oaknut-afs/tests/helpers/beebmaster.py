"""Test fixtures transcribed from Beebmaster's PDF.

"Understanding the Acorn Econet Level 3 File Server Structure" by ISW
(August 2010). Page references are to the PDF at
``/Users/rjs/Code/beebium/scripts/wfsinit/Understanding the Acorn
Level 3 File Server Structure.pdf``.

The document describes a specific test disc ("Level3MasterDisc")
prepared with WFSINIT on a blank ADFS-L floppy (160 cylinders, 16
sectors per track). Users BeebMaster and Games were added on top of
the automatic Syst user.

Every hex dump in the PDF is transcribed here as a Python bytes
literal, with the documented field interpretations available as
module-level constants. Tests use these to round-trip real-world
bytes through the oaknut.afs parsers and assert that the decoded
field values match what the PDF says they should.
"""

from __future__ import annotations

import datetime

# ---------------------------------------------------------------------------
# Info sector (NFS Sector 1 in the PDF's terminology)
#
# PDF page 6 — "First NFS Sector" hex dump. The full sector is at disc
# address 0x005010 (sector 0x51 = sector 1 of cylinder 5). Only the
# first 32+ bytes are non-zero.
# ---------------------------------------------------------------------------

INFO_SECTOR_BYTES: bytes = bytes.fromhex(
    # 0x00-0x0F: magic + start of disc name
    "41 46 53 30 4C 65 76 65 6C 33 4D 61 73 74 65 72"
    # 0x10-0x1F: rest of disc name + cylinders + total sectors +
    #            num discs + sectors per cylinder + bitmap size +
    #            addition factor + drive increment + start of root SIN
    "44 69 73 63 A0 00 00 0A 00 01 10 00 01 FF 01 71"
    # 0x20-0x2F: rest of root SIN + date + start cylinder +
    #            media flag + zero padding
    "00 00 28 D8 05 00 00 00 00 00 00 00 00 00 00 00"
).ljust(256, b"\x00")


# Field-by-field interpretation, as documented in the PDF's annotation
# block on page 6 (and corrected in our docs/afs-onwire.md for bytes
# 29/30 where the PDF disagreed with the ROM).

INFO_SECTOR_DISC_NAME = "Level3MasterDisc"
INFO_SECTOR_CYLINDERS = 0x00A0  # 160
INFO_SECTOR_TOTAL_SECTORS = 0x000A00  # 2560
INFO_SECTOR_NUM_DISCS = 1
INFO_SECTOR_SECTORS_PER_CYLINDER = 0x0010  # 16
INFO_SECTOR_BITMAP_SIZE = 1
INFO_SECTOR_ADDITION_FACTOR = 0xFF  # per ROM: "next physical disc" step
INFO_SECTOR_DRIVE_INCREMENT = 0x01  # per ROM: "next logical drive" step
INFO_SECTOR_ROOT_SIN = 0x000071  # sector 0x71 = sector 1 of cylinder 7
INFO_SECTOR_DATE = datetime.date(2010, 8, 8)  # packed 0xD828
INFO_SECTOR_START_CYLINDER = 5
INFO_SECTOR_MEDIA_FLAG = 0  # Winchester

# The PDF says the second copy (at sector 0x61, cylinder 6) is "identical".
INFO_SECTOR_COPY_BYTES: bytes = INFO_SECTOR_BYTES
