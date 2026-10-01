"""Invalid filenames are reported cleanly, once, on every filing system (#78)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.exception import ExitCode

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"


def _host_file(tmp_path: Path) -> Path:
    host = tmp_path / "host"
    host.write_bytes(b"data")
    return host


def _image(runner: CliRunner, tmp_path: Path, kind: str) -> Path:
    if kind == "afs":
        image = tmp_path / "t.dat"
        shutil.copy(_L3FS_DAT, image)
        shutil.copy(_L3FS_DSC, image.with_suffix(".dsc"))
        return image
    image = tmp_path / {"dfs": "t.ssd", "adfs": "t.adl", "romfs": "t.rom"}[kind]
    result = runner.invoke(cli, ["create", str(image)])
    assert result.exit_code == 0, result.output
    return image


def _assert_clean_once(result, message: str) -> None:
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code != 0
    assert result.output.count(message) == 1, result.output


class TestDFS:
    @pytest.mark.parametrize(
        ("name", "message"),
        [
            ("$.ABCDEFGHIJ", "Filename too long"),
            ("$.A:B", "Forbidden character ':'"),
        ],
    )
    def test_put_refuses_cleanly(self, runner, tmp_path, name, message):
        image = _image(runner, tmp_path, "dfs")
        result = runner.invoke(cli, ["put", f"{image}:{name}", str(_host_file(tmp_path))])
        _assert_clean_once(result, message)
        assert result.exit_code == ExitCode.DATA_ERR

    def test_mv_refuses_cleanly(self, runner, tmp_path):
        image = _image(runner, tmp_path, "dfs")
        runner.invoke(cli, ["put", f"{image}:$.OK", str(_host_file(tmp_path))])
        result = runner.invoke(cli, ["mv", f"{image}:$.OK", f"{image}:$.ABCDEFGHIJ"])
        _assert_clean_once(result, "Filename too long")


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("adfs", "$.ABCDEFGHIJKL"),
        ("afs", "afs:$.ABCDEFGHIJKL"),
        ("romfs", "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    ],
)
def test_put_reports_the_refusal_once(runner, tmp_path, kind, path):
    image = _image(runner, tmp_path, kind)
    result = runner.invoke(cli, ["put", f"{image}:{path}", str(_host_file(tmp_path))])
    _assert_clean_once(result, "Filename too long")


def test_adfs_mkdir_reports_the_refusal_once(runner, tmp_path):
    image = _image(runner, tmp_path, "adfs")
    result = runner.invoke(cli, ["mkdir", f"{image}:$.ABCDEFGHIJKL"])
    _assert_clean_once(result, "Filename too long")
