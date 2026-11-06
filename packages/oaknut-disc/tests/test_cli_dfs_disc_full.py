"""Writing to a full DFS disc reports a clean error, not a traceback (#97)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.exception import ExitCode


@pytest.fixture
def full_ssd(runner: CliRunner, tmp_path):
    image = tmp_path / "plain.ssd"
    assert runner.invoke(cli, ["create", str(image), "--title", "T"]).exit_code == 0
    return image


@pytest.fixture
def too_big(tmp_path):
    payload = tmp_path / "huge.bin"
    payload.write_bytes(bytes(250_000))  # 977 sectors; an 80-track disc has 798 free
    return payload


def test_put_reports_disc_full(runner: CliRunner, full_ssd, too_big):
    result = runner.invoke(cli, ["put", f"{full_ssd}:$.HUGE", str(too_big)])
    assert result.exit_code == ExitCode.CANT_CREATE, result.output
    assert "Not enough contiguous free space" in result.output
    assert "Traceback" not in result.output


def test_cp_reports_disc_full(runner: CliRunner, full_ssd, too_big, tmp_path):
    source = tmp_path / "source.adl"
    assert runner.invoke(cli, ["create", str(source)]).exit_code == 0
    assert runner.invoke(cli, ["put", f"{source}:$.HUGE", str(too_big)]).exit_code == 0
    result = runner.invoke(cli, ["cp", f"{source}:$.HUGE", f"{full_ssd}:$.HUGE"])
    assert result.exit_code == ExitCode.CANT_CREATE, result.output
    assert "Not enough contiguous free space" in result.output
