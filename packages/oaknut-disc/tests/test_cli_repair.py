"""disc repair applies the fixes validate's findings carry (#85).

Repair runs the same validation as ``disc validate`` and applies the fix
attached to each finding, so the two commands share their analysis and
cannot drift apart. The first fix rewrites a malformed DFS sector count
(#84) to the side's true size.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.exception import ExitCode

_SIDE_1_CATALOGUE = 0xA00


@pytest.fixture(params=[False, True], ids=["full", "trimmed"])
def malformed_dsd(request, runner: CliRunner, tmp_path: Path) -> Path:
    """A PanOS-like DSD: a file each side, both sector counts malformed."""
    image = tmp_path / "panos.dsd"
    assert runner.invoke(cli, ["create", str(image), "--title", "BOOT"]).exit_code == 0
    host = tmp_path / "payload"
    host.write_bytes(b"x" * 1000)
    for target in (f"{image}:$.FRONT", f"{image}::2.$.BACK"):
        assert (
            runner.invoke(cli, ["put", target, str(host), "--meta-format", "none"]).exit_code == 0
        )
    raw = bytearray(image.read_bytes())
    raw[0x106], raw[0x107] = 0x36, 0x40
    raw[_SIDE_1_CATALOGUE + 0x106], raw[_SIDE_1_CATALOGUE + 0x107] = 0x35, 0xDF
    if request.param:
        raw = raw[:407040]
    image.write_bytes(bytes(raw))
    return image


def _count_bytes(image: Path, catalogue: int) -> tuple[int, int]:
    raw = image.read_bytes()
    return raw[catalogue + 0x106], raw[catalogue + 0x107]


class TestRepair:
    def test_rewrites_each_side_to_its_true_size(self, runner, malformed_dsd):
        result = runner.invoke(cli, ["repair", str(malformed_dsd)])
        assert result.exit_code == 0, result.output
        # 800 sectors is &320; boot option 3 stays in bits 4-5; bits 2-3 clear.
        assert _count_bytes(malformed_dsd, 0) == (0x33, 0x20)
        assert _count_bytes(malformed_dsd, _SIDE_1_CATALOGUE) == (0x33, 0x20)

    def test_reports_each_repair_by_drive(self, runner, malformed_dsd):
        result = runner.invoke(cli, ["repair", str(malformed_dsd)])
        lines = result.output.splitlines()
        assert len(lines) == 2, result.output
        assert lines[0].startswith("drive :0: ")
        assert lines[1].startswith("drive :2: ")
        assert all("800" in line for line in lines)

    def test_leaves_a_disc_validate_passes(self, runner, malformed_dsd):
        runner.invoke(cli, ["repair", str(malformed_dsd)])
        result = runner.invoke(cli, ["validate", str(malformed_dsd)])
        assert result.exit_code == 0, result.output
        assert result.output == ""

    def test_keeps_the_files(self, runner, malformed_dsd):
        runner.invoke(cli, ["repair", str(malformed_dsd)])
        assert runner.invoke(cli, ["cat", f"{malformed_dsd}:$.FRONT"]).output == "x" * 1000
        assert runner.invoke(cli, ["cat", f"{malformed_dsd}::2.$.BACK"]).output == "x" * 1000

    def test_dry_run_reports_without_writing(self, runner, malformed_dsd):
        before = malformed_dsd.read_bytes()
        result = runner.invoke(cli, ["repair", "--dry-run", str(malformed_dsd)])
        assert result.exit_code == 0, result.output
        assert len(result.output.splitlines()) == 2
        assert "would" in result.output
        assert malformed_dsd.read_bytes() == before


class TestNothingToRepair:
    def test_a_clean_image_is_untouched_and_silent(self, runner, tmp_path):
        image = tmp_path / "clean.ssd"
        runner.invoke(cli, ["create", str(image), "--title", "OK"])
        before = image.read_bytes()
        result = runner.invoke(cli, ["repair", str(image)])
        assert (result.exit_code, result.output) == (0, "")
        assert image.read_bytes() == before

    def test_a_defect_with_no_fix_is_reported_and_left(self, runner, tmp_path):
        # One file claimed at sector 390 for 20 sectors on a 400-sector side.
        buffer = bytearray(102400)
        buffer[0:8] = b"BROKEN  "
        buffer[256:260] = b"    "
        buffer[261] = 8
        buffer[262], buffer[263] = 0x01, 0x90
        buffer[8:15] = b"A      "
        buffer[15] = ord("$")
        buffer[256 + 8 : 256 + 16] = bytes([0, 0, 0, 0, 0x00, 0x14, 0x01, 0x86])
        image = tmp_path / "bad.ssd"
        image.write_bytes(bytes(buffer))
        result = runner.invoke(cli, ["repair", str(image)])
        assert result.exit_code == ExitCode.DATA_ERR, result.output
        assert "extends beyond disk" in result.output
        assert image.read_bytes() == bytes(buffer)


def test_describe_filesystem_lists_the_repairs(runner):
    result = runner.invoke(cli, ["describe-filesystem", "acorn-dfs"])
    assert "Repairs:" in result.output
    assert "sector count" in result.output
