"""End-to-end `disc` CLI coverage for ROMFS images."""

from __future__ import annotations

import shutil

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

ROMFS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "romfs"
_HOPPER = ROMFS_DIRPATH / "Electron_Hopper.rom"  # plain, complete
_COUNTDOWN = ROMFS_DIRPATH / "Electron_Countdown_To_Doom_1.rom"  # composite
_SNAPPER_SSD = REFERENCE_IMAGES_DIRPATH / "games" / "Disc001-SnapperV2.ssd"  # a whole DFS game


class TestRomfsCrossCopy:
    def test_cp_into_rom_keeps_flat_names(self, runner: CliRunner, tmp_path):
        # Regression: copying a DFS file into a flat ROMFS must not leak the
        # DFS "$." root into the ROMFS name (cp once treated every flat
        # filesystem as DFS and remapped paths through its "$." model).
        ssd = tmp_path / "src.ssd"
        assert runner.invoke(cli, ["create", str(ssd), "--title", "SRC"]).exit_code == 0
        payload = tmp_path / "data.bin"
        payload.write_bytes(b"payload!")
        assert runner.invoke(cli, ["put", f"{ssd}:$.DATA", str(payload)]).exit_code == 0

        rom = tmp_path / "CART.rom"
        assert runner.invoke(cli, ["create", str(rom), "--title", "CART"]).exit_code == 0
        copied = runner.invoke(cli, ["cp", f"{ssd}:$.DATA", f"{rom}:DATA"])
        assert copied.exit_code == 0, copied.output

        listing = runner.invoke(cli, ["ls", str(rom)]).output
        assert "$." not in listing  # the name is flat "DATA", not "$.DATA"
        # And it is addressable by its flat name.
        assert runner.invoke(cli, ["cat", f"{rom}:DATA"]).stdout_bytes == b"payload!"

    def test_cp_from_ordered_disc_preserves_storage_order(self, runner: CliRunner, tmp_path):
        # The cartridge case: a game disc is laid out with its boot files in
        # the lowest sectors so they load first, and that order must survive
        # the copy into the ROM's sequential stream. The DFS catalogue is
        # stored highest-sector-first, so a copy that followed it would lay
        # the files into the ROM reversed — slow-loading on real hardware.
        from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS

        ssd = tmp_path / "game.ssd"
        with DFS.create_file(ssd, ACORN_DFS_80T_SINGLE_SIDED, title="GAME") as dfs:
            (dfs.root / "$.BOOT").write_bytes(b"b" * 400)  # lowest sectors
            (dfs.root / "$.LOADER").write_bytes(b"l" * 400)
            (dfs.root / "$.GAME").write_bytes(b"g" * 400)  # highest sectors

        rom = tmp_path / "CART.rom"
        assert runner.invoke(cli, ["create", str(rom), "--title", "CART"]).exit_code == 0
        copied = runner.invoke(cli, ["cp", f"{ssd}:$.*", f"{rom}:"])
        assert copied.exit_code == 0, copied.output

        def storage_order(target: str) -> list[str]:
            out = runner.invoke(cli, ["storage-order", target]).output
            # Rows are TSV "path<TAB>size"; take the path column only.
            return [
                line.split("\t")[0].strip()
                for line in out.splitlines()
                if line.strip() and not line.lstrip().startswith("#")
            ]

        # The disc's physical order, then the ROM's stream order — equal
        # leaf-for-leaf (ROMFS names are flat, the disc's carry the $ dir).
        source_leaves = [path.split(".")[-1] for path in storage_order(str(ssd))]
        assert source_leaves == ["BOOT", "LOADER", "GAME"]
        assert storage_order(str(rom)) == source_leaves


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
        # The cookbook "Create a game cartridge ROM" workflow: copy a whole
        # DFS game onto a fresh cartridge with disc cp, plus title/copyright.
        ssd = tmp_path / "snapper.ssd"
        shutil.copy(_SNAPPER_SSD, ssd)
        cart = tmp_path / "SNAPPER.rom"
        assert runner.invoke(cli, ["create", str(cart), "--title", "Snapper"]).exit_code == 0
        copyright_ = "(C) Acornsoft 1982"
        assert (
            runner.invoke(cli, ["romfs", "set-copyright", str(cart), copyright_]).exit_code == 0
        )
        # A bare image path (no trailing colon) resolves to the ROM's root.
        copied = runner.invoke(cli, ["cp", f"{ssd}:$.*", str(cart)])
        assert copied.exit_code == 0, copied.output

        listing = runner.invoke(cli, ["ls", str(cart)]).output
        for name in ("Snappe3", "SNAPPER", "!BOOT"):
            assert name in listing
        assert "$." not in listing  # flat ROMFS names, no DFS root leak
        # The DFS files were delete-locked; that must NOT become ROMFS's
        # *RUN-only bit (Access.X), or *EXEC !BOOT / CHAIN would fail "Locked".
        assert "X/" not in listing
        assert (
            runner.invoke(cli, ["romfs", "get-copyright", str(cart)]).output.strip() == copyright_
        )
        # A game file's bytes survived the copy onto the cartridge.
        from_ssd, from_rom = tmp_path / "a", tmp_path / "b"
        assert runner.invoke(cli, ["get", f"{ssd}:$.Snappe3", str(from_ssd)]).exit_code == 0
        assert runner.invoke(cli, ["get", f"{cart}:Snappe3", str(from_rom)]).exit_code == 0
        assert from_ssd.read_bytes() == from_rom.read_bytes()


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


class TestRomfsRunOnly:
    def _rom_with_file(self, runner: CliRunner, tmp_path):
        rom = tmp_path / "RO.rom"
        runner.invoke(cli, ["create", str(rom), "--title", "RO"])
        src = tmp_path / "game.bin"
        src.write_bytes(b"machine code")
        runner.invoke(cli, ["put", f"{rom}:GAME", str(src)])
        return rom

    def _attr(self, runner: CliRunner, rom) -> str:
        line = next(
            ln for ln in runner.invoke(cli, ["ls", str(rom)]).output.splitlines() if "GAME" in ln
        )
        return line.split()[-1]  # the Attr column

    def test_chmod_sets_the_run_only_bit(self, runner: CliRunner, tmp_path):
        rom = self._rom_with_file(runner, tmp_path)
        assert self._attr(runner, rom) == "/"  # newly put: loadable
        assert runner.invoke(cli, ["chmod", f"{rom}:GAME", "X"]).exit_code == 0
        assert self._attr(runner, rom) == "X/"  # now *RUN-only

    def test_chmod_clears_the_run_only_bit(self, runner: CliRunner, tmp_path):
        rom = self._rom_with_file(runner, tmp_path)
        runner.invoke(cli, ["chmod", f"{rom}:GAME", "X"])
        assert self._attr(runner, rom) == "X/"
        assert runner.invoke(cli, ["chmod", f"{rom}:GAME", "WR"]).exit_code == 0
        assert self._attr(runner, rom) == "/"  # cleared (R/W are not stored on ROMFS)
