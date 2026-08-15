"""New-directory (ADFS D format) reading and round-trip tests.

Rung 1 of New Map support: the New directory (2048 bytes, 77 entries,
ROR-13 check byte) sitting on the *Old* free-space map, as used by the
800K D format. File data is still contiguous, so these exercise the new
directory parser/serialiser without needing the zoned New Map.

Specimens are real Acorn OS distribution discs (see
``tests/data/images/adfs-riscos/README.md``).
"""

from __future__ import annotations

import shutil

from oaknut.adfs.adfs import ADFS, ADFS_D
from oaknut.adfs.directory import (
    NewDirectoryFormat,
    OldDirectoryFormat,
    _calculate_new_dir_check,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

RISCOS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-riscos"

# A D-format disc (Old map + New directory). !Configure..!System are
# application directories; DrawDemo/PaintDemo/ReadMe are files.
APP1 = RISCOS_DIRPATH / "D_RISCOS310_App1.adf"
WELCOME = RISCOS_DIRPATH / "D_Arthur_Welcome.adf"


def test_d_format_detected_as_new_directory():
    with ADFS.from_file(APP1) as adfs:
        assert isinstance(adfs._dir_format, NewDirectoryFormat)
        assert adfs._root_address == 4  # 0x400
        # 800K, addressed as a flat linear surface.
        assert adfs.total_size == ADFS_D.total_bytes


def test_d_format_root_listing():
    with ADFS.from_file(APP1) as adfs:
        names = [p.name for p in adfs.root.iterdir()]
    assert "!System" in names
    assert "ReadMe" in names
    # Directories sort with FileCore's case-insensitive ordering; just
    # assert the full expected membership regardless of order.
    assert set(names) == {
        "!Configure", "!Draw", "!Edit", "!Fonts", "!Help", "!Paint",
        "!PrinterDM", "!PrinterPS", "!System", "DrawDemo", "PaintDemo", "ReadMe",
    }


def test_d_format_root_title():
    with ADFS.from_file(APP1) as adfs:
        assert adfs.root.title == "0283,019-01"


def test_d_format_entry_attributes_from_atts_byte():
    with ADFS.from_file(APP1) as adfs:
        system = adfs.root / "!System"
        assert system.is_dir()
        readme = adfs.root / "ReadMe"
        stat = readme.stat()
        assert not stat.is_directory
        assert stat.owner_read and stat.owner_write
        assert stat.length == 2290


def test_d_format_read_file_data():
    with ADFS.from_file(APP1) as adfs:
        data = (adfs.root / "ReadMe").read_bytes()
    assert len(data) == 2290
    # The Acorn ReadMe is plain text.
    assert data[:1].isascii()
    assert b"\r" in data or b"\n" in data


def test_d_format_descend_subdirectory():
    with ADFS.from_file(APP1) as adfs:
        system = adfs.root / "!System"
        children = [p.name for p in system.iterdir()]
        # !System always carries a !Boot and a Modules directory.
        assert children  # non-empty
        for child in system.iterdir():
            # Every child resolves and stats without error.
            child.stat()


def test_new_dir_check_roundtrips_on_reserialise(tmp_path):
    """Rewriting the root (via a title change) keeps a valid check byte."""
    work = tmp_path / "app1.adf"
    shutil.copyfile(APP1, work)
    with ADFS.from_file(work) as adfs:
        adfs.root.title = "OAKNUT TEST"
    # Re-open: parse() re-validates signature, tail and ROR-13 check byte.
    with ADFS.from_file(work) as adfs:
        assert adfs.root.title == "OAKNUT TEST"
        names = {p.name for p in adfs.root.iterdir()}
        assert "!System" in names


def test_new_dir_check_matches_stored_on_all_specimens():
    for image in (APP1, WELCOME):
        raw = image.read_bytes()
        block = raw[0x400 : 0x400 + 2048]
        assert _calculate_new_dir_check(block) == block[0x7FF]


def test_sml_still_old_directory():
    """S/M/L discs keep the Old directory format and root at sector 2."""
    bcpl = REFERENCE_IMAGES_DIRPATH / "adfs-linear" / "BCPL.adf"
    with ADFS.from_file(bcpl) as adfs:
        assert isinstance(adfs._dir_format, OldDirectoryFormat)
        assert adfs._root_address == 2
