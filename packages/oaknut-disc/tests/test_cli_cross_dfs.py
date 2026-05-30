"""End-to-end CLI test for cross-DFS copying that exploits Watford capacity.

Acorn DFS caps a disc at 31 files — exactly a month's worth of daily
telemetry — so four months of 1984 temperature data live on four separate
single-sided Acorn discs. Watford DFS extends the catalogue to 62 files
per side, so a single double-sided Watford disc consolidates all four:
two months on each side. This exercises a non-Acorn DFS variant and a
copy from one DFS to another.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_TELEMETRY_DIRPATH = REFERENCE_IMAGES_DIRPATH / "telemetry"

# (source image, month digits, day count) — January to April 1984.
_MONTHS = [
    ("telem-8401.ssd", "01", 31),
    ("telem-8402.ssd", "02", 29),  # 1984 is a leap year
    ("telem-8403.ssd", "03", 31),
    ("telem-8404.ssd", "04", 30),
]


def _names_on(runner: CliRunner, compound_path: str) -> set[str]:
    result = runner.invoke(cli, ["ls", "--as", "display", compound_path])
    assert result.exit_code == 0, result.output
    return {tok for line in result.output.splitlines() for tok in line.split()}


@pytest.fixture
def telemetry_dir(tmp_path: Path) -> Path:
    """The four monthly Acorn SSDs copied into a writable working dir."""
    for source_name, _mm, _days in _MONTHS:
        shutil.copy(_TELEMETRY_DIRPATH / source_name, tmp_path / source_name)
    return tmp_path


class TestConsolidateTelemetryOntoWatford:
    def test_four_acorn_months_onto_one_watford_disc(
        self, runner: CliRunner, telemetry_dir: Path
    ) -> None:
        telem = telemetry_dir / "telem.dsd"

        created = runner.invoke(cli, ["create", str(telem), "--filesystem", "watford-dfs"])
        assert created.exit_code == 0, created.output

        # Two months per Watford side — 60 and 61 files, each past Acorn's 31.
        for source_name, _mm, _days in _MONTHS[:2]:
            r = runner.invoke(cli, ["cp", f"{telemetry_dir / source_name}:$.*", f"{telem}::0.$."])
            assert r.exit_code == 0, r.output
        for source_name, _mm, _days in _MONTHS[2:]:
            r = runner.invoke(cli, ["cp", f"{telemetry_dir / source_name}:$.*", f"{telem}::2.$."])
            assert r.exit_code == 0, r.output

        side0 = _names_on(runner, f"{telem}::0.$")
        side2 = _names_on(runner, f"{telem}::2.$")
        # 31 (Jan) + 29 (Feb) = 60 on side 0; 31 (Mar) + 30 (Apr) = 61 on side 2.
        assert len([n for n in side0 if n.startswith("84")]) == 60
        assert len([n for n in side2 if n.startswith("84")]) == 61
        # Each side holds its own two months and not the other's.
        assert "840115" in side0 and "840229" in side0  # Jan 15, Feb 29 (leap day)
        assert "840315" in side2 and "840430" in side2  # Mar 15, Apr 30
        assert not any(n.startswith(("8403", "8404")) for n in side0)
        assert not any(n.startswith(("8401", "8402")) for n in side2)

    def test_disc_is_watford_and_valid(self, runner: CliRunner, telemetry_dir: Path) -> None:
        telem = telemetry_dir / "telem.dsd"
        assert runner.invoke(cli, ["create", str(telem), "--filesystem", "watford-dfs"]).exit_code == 0
        src = telemetry_dir / "telem-8401.ssd"
        assert runner.invoke(cli, ["cp", f"{src}:$.*", f"{telem}::0.$."]).exit_code == 0

        identified = runner.invoke(cli, ["identify", str(telem)])
        assert identified.exit_code == 0, identified.output
        assert "watford-dfs" in identified.output

        validated = runner.invoke(cli, ["validate", str(telem)])
        assert validated.exit_code == 0, validated.output

    def test_file_content_round_trips_across_dfs_variants(
        self, runner: CliRunner, telemetry_dir: Path
    ) -> None:
        telem = telemetry_dir / "telem.dsd"
        src = telemetry_dir / "telem-8403.ssd"
        runner.invoke(cli, ["create", str(telem), "--filesystem", "watford-dfs"])
        runner.invoke(cli, ["cp", f"{src}:$.*", f"{telem}::2.$."])

        # The same bytes read from the Acorn source and the Watford copy.
        from_acorn = runner.invoke(cli, ["cat", f"{src}:$.840315"])
        from_watford = runner.invoke(cli, ["cat", f"{telem}::2.$.840315"])
        assert from_acorn.exit_code == 0 and from_watford.exit_code == 0
        assert from_watford.stdout_bytes == from_acorn.stdout_bytes
        # 24 hourly readings, carriage-return separated.
        assert from_watford.stdout_bytes.count(b"\r") == 24
