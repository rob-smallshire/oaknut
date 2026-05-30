"""End-to-end `disc` CLI coverage for ROMFS images."""

from __future__ import annotations

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"
_HOPPER = ROMFS_DIRPATH / "Electron_Hopper.rom"  # plain, complete
_COUNTDOWN = ROMFS_DIRPATH / "Electron_Countdown_To_Doom_1.rom"  # composite


class TestRomfsIdentifyAndList:
    def test_identify(self, runner: CliRunner):
        result = runner.invoke(cli, ["identify", str(_HOPPER)])
        assert result.exit_code == 0
        assert "acorn-romfs" in result.output

    def test_ls(self, runner: CliRunner):
        result = runner.invoke(cli, ["ls", str(_HOPPER)])
        assert result.exit_code == 0
        assert "HOPOBJ" in result.output


class TestRomfsStatNotes:
    def test_plain_rom_has_no_notes(self, runner: CliRunner):
        result = runner.invoke(cli, ["stat", str(_HOPPER)])
        assert result.exit_code == 0
        assert "Notes" not in result.output

    def test_composite_rom_reports_read_only(self, runner: CliRunner):
        result = runner.invoke(cli, ["stat", str(_COUNTDOWN)])
        assert result.exit_code == 0
        assert "Notes" in result.output
        assert "read-only" in result.output
