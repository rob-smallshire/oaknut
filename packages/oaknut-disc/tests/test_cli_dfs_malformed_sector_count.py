"""DFS discs whose sector-count field is malformed (#84).

The PanOS 1.40 installation discs are ordinary Acorn DFS discs whose
catalogue headers carry a malformed sector count: side 0 ``&36 &40``
(1600 sectors, with bit 2 of &106 set — Opus DDOS's 11-bit count) and
side 1 ``&35 &DF`` (an 11-bit 1503). Their catalogues and files are
sound, and the images stop short of a full disc (407040 of 409600
bytes). The analogue here is built from scratch: a fresh 80-track
double-sided disc with a file on each side, given those header bytes,
both full-length and trimmed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.exception import ExitCode

_SIDE_1_CATALOGUE = 0xA00  # track 0 of side 1 in an interleaved DSD
_SIDE_BYTES = 800 * 256


@pytest.fixture(params=[False, True], ids=["full", "trimmed"])
def malformed_dsd(request, runner: CliRunner, tmp_path: Path) -> Path:
    image = tmp_path / "panos.dsd"
    assert runner.invoke(cli, ["create", str(image), "--title", "BOOT"]).exit_code == 0
    host = tmp_path / "payload"
    host.write_bytes(b"x" * 1000)
    for target in (f"{image}:$.FRONT", f"{image}::2.$.BACK"):
        result = runner.invoke(cli, ["put", target, str(host), "--meta-format", "none"])
        assert result.exit_code == 0, result.output
    raw = bytearray(image.read_bytes())
    raw[0x106], raw[0x107] = 0x36, 0x40  # side 0: boot 3, 11-bit count 1600
    raw[_SIDE_1_CATALOGUE + 0x106], raw[_SIDE_1_CATALOGUE + 0x107] = 0x35, 0xDF  # 1503
    if request.param:
        raw = raw[:407040]  # stop short of a full disc, as the PanOS images do
    image.write_bytes(bytes(raw))
    return image


def _names(output: str) -> set[str]:
    return {r.split("\t")[0] for r in output.splitlines() if r and not r.startswith("#")}


class TestRecognised:
    def test_side_0_lists_without_forcing(self, runner, malformed_dsd):
        result = runner.invoke(cli, ["ls", "--as", "tsv", f"{malformed_dsd}:$"])
        assert result.exit_code == 0, result.output
        assert "FRONT" in _names(result.output)

    def test_side_1_lists_without_forcing(self, runner, malformed_dsd):
        result = runner.invoke(cli, ["ls", "--as", "tsv", f"{malformed_dsd}::2.$"])
        assert result.exit_code == 0, result.output
        assert "BACK" in _names(result.output)

    def test_each_side_is_sized_by_the_image(self, runner, malformed_dsd):
        result = runner.invoke(cli, ["stat", "--as", "tsv", str(malformed_dsd)])
        assert result.exit_code == 0, result.output
        sizes = [
            r.split("\t")[1]
            for r in result.output.splitlines()
            if r.lstrip("# ").startswith("Size\t")
        ]
        assert sizes == [str(_SIDE_BYTES)] * 2


class TestReported:
    def test_validate_reports_the_malformed_field_on_every_side(self, runner, malformed_dsd):
        result = runner.invoke(cli, ["validate", str(malformed_dsd)])
        assert result.exit_code == ExitCode.DATA_ERR, result.output
        assert "declares 1600 sectors" in result.output
        assert "declares 1503 sectors" in result.output
        assert "the side holds 800" in result.output

    def test_identify_notes_the_malformed_field(self, runner, malformed_dsd):
        result = runner.invoke(
            cli, ["identify", "--report", "candidates", "--as", "tsv", str(malformed_dsd)]
        )
        assert result.exit_code == 0, result.output
        assert "acorn-dfs" in result.output
        assert "malformed sector count" in result.output


class TestStillStrict:
    def test_reserved_bits_with_no_file_table_to_corroborate_are_rejected(self, runner, tmp_path):
        image = tmp_path / "junk.ssd"
        raw = bytearray(204800)
        raw[0x106] = 0x04  # bit 2 set, and no files to corroborate
        image.write_bytes(bytes(raw))
        assert runner.invoke(cli, ["ls", str(image)]).exit_code != 0

    def test_bits_6_and_7_still_disqualify(self, runner, malformed_dsd):
        raw = bytearray(malformed_dsd.read_bytes())
        raw[0x106] |= 0x40
        malformed_dsd.write_bytes(bytes(raw))
        result = runner.invoke(cli, ["ls", str(malformed_dsd)])
        assert result.exit_code != 0
        assert "reserved bits" in result.output


def test_validate_skips_a_blank_second_side_and_still_reports_the_first(runner, tmp_path):
    # PanOS14-2.dsd: side 0 malformed, side 1 never formatted (all zeros).
    image = tmp_path / "blank-back.dsd"
    assert runner.invoke(cli, ["create", str(image), "--title", "SYS"]).exit_code == 0
    host = tmp_path / "payload"
    host.write_bytes(b"x" * 1000)
    runner.invoke(cli, ["put", f"{image}:$.FRONT", str(host), "--meta-format", "none"])
    raw = bytearray(image.read_bytes())
    raw[0x106], raw[0x107] = 0x36, 0x40
    raw[_SIDE_1_CATALOGUE : _SIDE_1_CATALOGUE + 512] = bytes(512)
    image.write_bytes(bytes(raw))
    result = runner.invoke(cli, ["validate", str(image)])
    assert result.exit_code == ExitCode.DATA_ERR, result.output
    assert "declares 1600 sectors" in result.output
    assert "not a valid" not in result.output


def test_an_owlet_disc_is_reported_for_its_bogus_total(runner):
    # Owlet (bbcmicrobot.com) writes a sector count of 3 on an otherwise
    # sound 80-track disc: recognised as before, and now reported.
    from tests.fixtures import REFERENCE_IMAGES_DIRPATH

    image = REFERENCE_IMAGES_DIRPATH / "owlet" / "owlet-dla.ssd"
    result = runner.invoke(cli, ["validate", str(image)])
    assert result.exit_code == ExitCode.DATA_ERR, result.output
    assert "declares 3 sectors" in result.output
    assert "positive multiple of ten" in result.output
