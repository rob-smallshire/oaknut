"""End-to-end `disc` CLI coverage for ROMFS images."""

from __future__ import annotations

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"
_HOPPER = ROMFS_DIRPATH / "Electron_Hopper.rom"  # plain, complete
_COUNTDOWN = ROMFS_DIRPATH / "Electron_Countdown_To_Doom_1.rom"  # composite
_ZALAGA = ROMFS_DIRPATH / "Zalaga.rom"  # a single machine-code game file


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

    def test_overfilling_a_rom_is_a_clean_error(self, runner: CliRunner, tmp_path):
        rom = tmp_path / "SMALL.rom"
        assert (
            runner.invoke(
                cli, ["create", str(rom), "--filesystem", "acorn-romfs", "--geometry", "8k"]
            ).exit_code
            == 0
        )
        big = tmp_path / "big.bin"
        big.write_bytes(b"\x00" * 9000)  # larger than an 8 KiB ROM

        result = runner.invoke(cli, ["put", f"{rom}:BIG", str(big)])
        assert result.exit_code != 0
        # A clean, accurate diagnostic — not a traceback, and not the
        # misleading "would overwrite content" wording (this ROM is plain).
        assert "Traceback" not in result.output
        assert "ROM full" in result.output
        assert "too large for this 8 KiB ROM" in result.output
        # The failed write left the ROM untouched.
        assert "BIG" not in runner.invoke(cli, ["ls", str(rom)]).output

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

    def test_build_a_game_cartridge(self, runner: CliRunner, tmp_path):
        # The cookbook "Create a game cartridge ROM" workflow: lift a game
        # out of one ROM and re-cartridge it with a title and copyright.
        game = tmp_path / "ZALAGA"
        assert runner.invoke(cli, ["get", f"{_ZALAGA}:ZALAGA", str(game)]).exit_code == 0

        cart = tmp_path / "ZALAGA.rom"
        assert runner.invoke(cli, ["create", str(cart), "--title", "Zalaga"]).exit_code == 0
        copyright_ = "(C) Nick Pelling & Mike Tomlinson"
        assert (
            runner.invoke(cli, ["romfs", "set-copyright", str(cart), copyright_]).exit_code == 0
        )
        assert (
            runner.invoke(
                cli,
                ["put", f"{cart}:ZALAGA", str(game), "--load", "0x3000", "--exec", "0x4522"],
            ).exit_code
            == 0
        )

        assert "ZALAGA" in runner.invoke(cli, ["ls", str(cart)]).output
        assert (
            runner.invoke(cli, ["romfs", "get-copyright", str(cart)]).output.strip() == copyright_
        )
        # The game bytes survived the round-trip onto the new cartridge.
        back = tmp_path / "ZALAGA.out"
        assert runner.invoke(cli, ["get", f"{cart}:ZALAGA", str(back)]).exit_code == 0
        assert back.read_bytes() == game.read_bytes()


class TestRomfsProperties:
    def _make(self, runner: CliRunner, tmp_path) -> str:
        rom = tmp_path / "PROPS.rom"
        runner.invoke(cli, ["create", str(rom), "--title", "PROPS"])
        return str(rom)

    def test_get_copyright_and_version(self, runner: CliRunner, tmp_path):
        rom = self._make(runner, tmp_path)
        assert runner.invoke(cli, ["romfs", "get-copyright", rom]).output.strip() == "(C) oaknut"
        assert runner.invoke(cli, ["romfs", "get-version", rom]).output.strip() == "1"

    def test_set_version_round_trips(self, runner: CliRunner, tmp_path):
        rom = self._make(runner, tmp_path)
        assert runner.invoke(cli, ["romfs", "set-version", rom, "7"]).exit_code == 0
        assert runner.invoke(cli, ["romfs", "get-version", rom]).output.strip() == "7"

    def test_set_version_accepts_hex(self, runner: CliRunner, tmp_path):
        # Like the address commands, the value honours a base prefix.
        rom = self._make(runner, tmp_path)
        assert runner.invoke(cli, ["romfs", "set-version", rom, "0x2A"]).exit_code == 0
        assert runner.invoke(cli, ["romfs", "get-version", rom]).output.strip() == "42"

    def test_set_copyright_round_trips(self, runner: CliRunner, tmp_path):
        rom = self._make(runner, tmp_path)
        result = runner.invoke(cli, ["romfs", "set-copyright", rom, "(C) 1984 Acornsoft"])
        assert result.exit_code == 0, result.output
        assert (
            runner.invoke(cli, ["romfs", "get-copyright", rom]).output.strip()
            == "(C) 1984 Acornsoft"
        )
        # The ROM is still valid after the rebuild.
        assert "acorn-romfs" in runner.invoke(cli, ["identify", rom]).output

    def test_bad_copyright_is_a_clean_error(self, runner: CliRunner, tmp_path):
        rom = self._make(runner, tmp_path)
        result = runner.invoke(cli, ["romfs", "set-copyright", rom, "no mark"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert "(C)" in result.output

    def test_set_version_rejects_out_of_range(self, runner: CliRunner, tmp_path):
        rom = self._make(runner, tmp_path)
        assert runner.invoke(cli, ["romfs", "set-version", rom, "999"]).exit_code != 0
