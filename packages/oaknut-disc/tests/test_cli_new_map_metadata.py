"""CLI metadata verbs against New Map / RISC OS ADFS images.

The metadata commands (stat, ls, get/set filetype and datestamp, get/set
load/exec) were verified against old-map ADFS, but the RISC OS family — the
New directory (D) and New map (E/F/G, E+/F+/G+) layouts — reaches them only
once content identification recognises the disc. These tests exercise the
whole path: identify -> mount -> read/write metadata, on both a created New
map disc and the shipped RISC OS specimens.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.adfs import ADFS, ADFS_E
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_RISCOS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-riscos"
_NEWLOOK = _RISCOS_DIRPATH / "E_RISCOS310_NewLook.adf"


def _run(runner, *args):
    return runner.invoke(cli, list(args))


@pytest.fixture
def new_map_image_filepath(tmp_path: Path) -> Path:
    """A blank New map (E) floppy carrying one addressed file."""
    filepath = tmp_path / "newmap.adf"
    with ADFS.create_file(str(filepath), ADFS_E, title="NewMapMeta") as adfs:
        (adfs.root / "Hello").write_bytes(
            b"Hello New Map", load_address=0x1900, exec_address=0x8023
        )
    return filepath


class TestCreatedNewMapMetadata:
    def test_identify_recognises_new_map(self, runner: CliRunner, new_map_image_filepath: Path):
        out = _run(runner, "identify", str(new_map_image_filepath))
        assert out.exit_code == 0, out.output
        assert "adfs" in out.output

    def test_set_get_filetype_round_trips(
        self, runner: CliRunner, new_map_image_filepath: Path
    ):
        target = f"{new_map_image_filepath}:$.Hello"
        assert _run(runner, "set-filetype", target, "Text").exit_code == 0
        got = _run(runner, "get-filetype", "--as", "display", target)
        assert got.exit_code == 0, got.output
        assert "Text" in got.output

    def test_set_get_datestamp_round_trips(
        self, runner: CliRunner, new_map_image_filepath: Path
    ):
        target = f"{new_map_image_filepath}:$.Hello"
        assert _run(runner, "set-datestamp", target, "1995-06-15T12:30:45").exit_code == 0
        got = _run(runner, "get-datestamp", "--as", "display", target)
        assert got.exit_code == 0, got.output
        assert "1995-06-15T12:30:45" in got.output

    def test_ls_detailed_shows_metadata_columns(
        self, runner: CliRunner, new_map_image_filepath: Path
    ):
        _run(runner, "set-filetype", f"{new_map_image_filepath}:$.Hello", "Text")
        out = _run(runner, "ls", "--as", "display", "--detailed", f"{new_map_image_filepath}:$")
        assert out.exit_code == 0, out.output
        assert "Filetype" in out.output and "Datestamp" in out.output

    def test_metadata_write_keeps_disc_valid(
        self, runner: CliRunner, new_map_image_filepath: Path
    ):
        target = f"{new_map_image_filepath}:$.Hello"
        _run(runner, "set-filetype", target, "&FFB")
        _run(runner, "set-datestamp", target, "1995-06-15T12:30:45")
        with ADFS.from_file(new_map_image_filepath, read_only=True) as adfs:
            assert adfs.is_new_map
            assert adfs.validate() == []


class TestRiscOsSpecimenMetadata:
    """Read-only verbs against the committed E-format RISC OS specimen."""

    def test_identify(self, runner: CliRunner):
        out = _run(runner, "identify", str(_NEWLOOK))
        assert out.exit_code == 0, out.output
        assert "adfs" in out.output

    def test_stat_reports_filetype_and_datestamp(self, runner: CliRunner):
        out = _run(runner, "stat", "--as", "display", f"{_NEWLOOK}:$.!NewLook.!RunImage")
        assert out.exit_code == 0, out.output
        # !RunImage is BASIC (&FFB), datestamped 1993.
        assert "1993-03-15" in out.output

    def test_get_filetype_display(self, runner: CliRunner):
        out = _run(
            runner, "get-filetype", "--as", "display", f"{_NEWLOOK}:$.!NewLook.!RunImage"
        )
        assert out.exit_code == 0, out.output
        assert "BASIC" in out.output

    def test_ls_detailed_lists_typed_files(self, runner: CliRunner):
        out = _run(runner, "ls", "--as", "display", "--detailed", f"{_NEWLOOK}:$.!NewLook")
        assert out.exit_code == 0, out.output
        assert "Filetype" in out.output
