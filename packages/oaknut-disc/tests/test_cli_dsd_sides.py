"""End-to-end CLI tests for addressing both sides of a double-sided DFS image.

These mirror the user workflow that surfaced the feature: assembling a
double-sided ``.dsd`` from two single-sided ``.ssd`` images, and the
reverse — splitting a ``.dsd`` back into two ``.ssd`` images. The second
side is reached with verbatim Acorn drive syntax, ``image::2.$``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.dfs import ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED as DSD
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED as SSD
from oaknut.dfs import DFS
from oaknut.disc.cli import cli


def _make_ssd(filepath: Path, title: str, files: dict[str, bytes]) -> Path:
    with DFS.create_file(filepath, SSD, title=title) as dfs:
        for name, data in files.items():
            (dfs.root / f"$.{name}").write_bytes(data)
    return filepath


def _make_dsd(filepath: Path, side0: dict[str, bytes], side2: dict[str, bytes]) -> Path:
    with DFS.create_file(filepath, DSD, title="FRONT") as s0:
        for name, data in side0.items():
            (s0.root / f"$.{name}").write_bytes(data)
    with DFS.from_file(filepath, DSD, side=1) as s2:
        s2.title = "REAR"
        for name, data in side2.items():
            (s2.root / f"$.{name}").write_bytes(data)
    return filepath


def _names_on(runner: CliRunner, compound_path: str) -> set[str]:
    result = runner.invoke(cli, ["ls", "--as", "display", compound_path])
    assert result.exit_code == 0, result.output
    return {tok for line in result.output.splitlines() for tok in line.split()}


class TestBuildDsdFromTwoSsds:
    """The headline workflow: two SSDs → one DSD, a side each."""

    def test_assemble_and_each_side_holds_its_own(self, runner: CliRunner, tmp_path: Path) -> None:
        drive0 = _make_ssd(
            tmp_path / "drive-0.ssd", "ZERO", {"PROG0": b"prog zero", "DATA0": b"00"}
        )
        drive2 = _make_ssd(tmp_path / "drive-2.ssd", "TWO", {"PROG2": b"prog two", "DATA2": b"22"})
        compendium = tmp_path / "compendium.dsd"

        created = runner.invoke(cli, ["create", str(compendium), "--title", "Compendium E"])
        assert created.exit_code == 0, created.output

        # Mark's workflow: copy each SSD's catalogue onto its own side.
        cp0 = runner.invoke(cli, ["cp", f"{drive0}:$.*", f"{compendium}:$/"])
        assert cp0.exit_code == 0, cp0.output
        cp2 = runner.invoke(cli, ["cp", f"{drive2}:$.*", f"{compendium}::2.$/"])
        assert cp2.exit_code == 0, cp2.output

        side0 = _names_on(runner, f"{compendium}:$")
        side2 = _names_on(runner, f"{compendium}::2.$")
        assert {"PROG0", "DATA0"} <= side0
        assert {"PROG2", "DATA2"} <= side2
        # The two sides are independent volumes — neither carries the other's.
        assert not ({"PROG2", "DATA2"} & side0)
        assert not ({"PROG0", "DATA0"} & side2)

    def test_file_content_round_trips_on_second_side(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        drive2 = _make_ssd(tmp_path / "drive-2.ssd", "TWO", {"ELITE": b"\x10\x20 game image"})
        compendium = tmp_path / "compendium.dsd"
        assert runner.invoke(cli, ["create", str(compendium)]).exit_code == 0
        assert (
            runner.invoke(cli, ["cp", f"{drive2}:$.ELITE", f"{compendium}::2.$.ELITE"]).exit_code
            == 0
        )
        got = runner.invoke(cli, ["cat", f"{compendium}::2.$.ELITE"])
        assert got.exit_code == 0, got.output
        assert got.stdout_bytes == b"\x10\x20 game image"


class TestSplitDsdIntoTwoSsds:
    """The reverse: one DSD → two SSDs, one per side."""

    def test_extract_each_side_to_its_own_ssd(self, runner: CliRunner, tmp_path: Path) -> None:
        source = _make_dsd(
            tmp_path / "compendium.dsd",
            side0={"FRONTA": b"front a", "FRONTB": b"front b"},
            side2={"REARA": b"rear a", "REARB": b"rear b"},
        )
        out0 = tmp_path / "out-0.ssd"
        out2 = tmp_path / "out-2.ssd"
        assert runner.invoke(cli, ["create", str(out0)]).exit_code == 0
        assert runner.invoke(cli, ["create", str(out2)]).exit_code == 0

        ex0 = runner.invoke(cli, ["cp", f"{source}:$.*", f"{out0}:$/"])
        assert ex0.exit_code == 0, ex0.output
        ex2 = runner.invoke(cli, ["cp", f"{source}::2.$.*", f"{out2}:$/"])
        assert ex2.exit_code == 0, ex2.output

        assert {"FRONTA", "FRONTB"} <= _names_on(runner, f"{out0}:$")
        assert {"REARA", "REARB"} <= _names_on(runner, f"{out2}:$")
        # Each extracted SSD carries only its own side's files.
        assert not ({"REARA", "REARB"} & _names_on(runner, f"{out0}:$"))
        assert not ({"FRONTA", "FRONTB"} & _names_on(runner, f"{out2}:$"))


class TestStatListsVolumes:
    """``disc stat`` on a DSD lists both sides under their designations."""

    def test_stat_shows_both_drives(self, runner: CliRunner, tmp_path: Path) -> None:
        dsd = _make_dsd(
            tmp_path / "two.dsd", side0={"FRONTF": b"f"}, side2={"REARF": b"r", "REARG": b"g"}
        )
        result = runner.invoke(cli, ["stat", "--as", "display", str(dsd)])
        assert result.exit_code == 0, result.output
        # Each side appears under the designation that addresses it.
        assert "Drive :0" in result.output
        assert "Drive :2" in result.output
        # Each side's own title is reported (independent volumes).
        assert "FRONT" in result.output
        assert "REAR" in result.output

    def test_stat_single_sided_is_flat(self, runner: CliRunner, tmp_path: Path) -> None:
        ssd = _make_ssd(tmp_path / "one.ssd", "SOLO", {"X": b"x"})
        result = runner.invoke(cli, ["stat", str(ssd)])
        assert result.exit_code == 0, result.output
        # No drive designations for a single, undesignated volume.
        assert ":0" not in result.output
        assert "Drive" not in result.output
        assert "SOLO" in result.output


class TestDriveSideErrors:
    """Addressing a side that is not there fails cleanly, by designation."""

    def test_drive_two_on_single_sided_is_clean(self, runner: CliRunner, tmp_path: Path) -> None:
        ssd = _make_ssd(tmp_path / "single.ssd", "ONE", {"ONLY": b"x"})
        result = runner.invoke(cli, ["ls", f"{ssd}::2.$"])
        assert result.exit_code != 0
        assert "Traceback" not in result.output
        assert ":2" in result.output
        assert "surface" not in result.output.lower()
