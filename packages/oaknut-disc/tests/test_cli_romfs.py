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


class TestRomfsCreate:
    def test_create_infers_romfs_from_rom_extension(self, runner: CliRunner, tmp_path):
        rom = tmp_path / "MYDISC.rom"
        result = runner.invoke(cli, ["create", str(rom), "--title", "MYDISC"])
        assert result.exit_code == 0, result.output
        assert rom.stat().st_size == 16384  # default size

        identified = runner.invoke(cli, ["identify", str(rom)])
        assert "acorn-romfs" in identified.output
        statted = runner.invoke(cli, ["stat", str(rom)])
        assert "MYDISC" in statted.output

    def test_create_8k_via_geometry(self, runner: CliRunner, tmp_path):
        rom = tmp_path / "SMALL.rom"
        result = runner.invoke(
            cli, ["create", str(rom), "--filesystem", "acorn-romfs", "--geometry", "8k"]
        )
        assert result.exit_code == 0, result.output
        assert rom.stat().st_size == 8192

    def test_create_then_put_a_file_in_and_back_out(self, runner: CliRunner, tmp_path):
        rom = tmp_path / "WORK.rom"
        assert runner.invoke(cli, ["create", str(rom), "--title", "WORK"]).exit_code == 0

        source = tmp_path / "hello.txt"
        source.write_bytes(b"Acorn ROMFS")
        put_in = runner.invoke(cli, ["put", f"{rom}:HELLO", str(source)])
        assert put_in.exit_code == 0, put_in.output

        listed = runner.invoke(cli, ["ls", str(rom)])
        assert "HELLO" in listed.output
        dumped = runner.invoke(cli, ["cat", f"{rom}:HELLO"])
        assert dumped.stdout_bytes == b"Acorn ROMFS"
