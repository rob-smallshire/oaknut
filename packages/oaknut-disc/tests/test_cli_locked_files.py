"""A locked file is not overwritten unless the command is forced.

Locked means the file may not be deleted, renamed or overwritten; on a
real machine ``*SAVE`` over a locked file fails with "Locked". ``disc put``
refuses a locked destination unless given ``-f``, ``disc cp -f`` replaces
one, and neither ever surfaces a traceback. See issue #62.
"""

from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner
from exit_codes import ExitCode
from oaknut.disc.cli import cli
from oaknut.disc.mount import resolve_mount

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"

_KINDS = ["dfs", "adfs", "afs"]


def _invoke(*args, input=None):
    return CliRunner().invoke(cli, [str(arg) for arg in args], input=input)


def _run(*args, input=None):
    result = _invoke(*args, input=input)
    assert result.exit_code == 0, (args, result.output)
    return result


def _image(tmp_path, kind: str, stem: str = "disc"):
    suffix = {"dfs": "ssd", "adfs": "adl", "afs": "dat"}[kind]
    filepath = tmp_path / f"{stem}.{suffix}"
    if kind == "afs":
        shutil.copy(_L3FS_DAT, filepath)
        shutil.copy(_L3FS_DSC, filepath.with_suffix(".dsc"))
    else:
        _run("create", filepath)
    return filepath


def _path(filepath, kind: str, leaf: str = "F") -> str:
    inner = f"afs:$.{leaf}" if kind == "afs" else f"$.{leaf}"
    return f"{filepath}:{inner}"


def _data(compound_path: str) -> bytes:
    with resolve_mount(compound_path) as resolved:
        return resolved.mount.read_bytes(resolved.path)


def _locked_file(tmp_path, kind: str) -> str:
    target = _path(_image(tmp_path, kind), kind)
    _run("put", target, "-", input="original")
    _run("chmod", target, "L")
    return target


@pytest.mark.parametrize("kind", _KINDS)
def test_put_refuses_a_locked_file(tmp_path, kind):
    target = _locked_file(tmp_path, kind)
    result = _invoke("put", target, "-", input="replacement")
    assert result.exit_code == ExitCode.NO_PERM
    assert "Traceback" not in result.output
    assert "locked" in result.output.lower()
    assert _data(target) == b"original"


@pytest.mark.parametrize("kind", _KINDS)
def test_put_force_replaces_a_locked_file(tmp_path, kind):
    target = _locked_file(tmp_path, kind)
    _run("put", "-f", target, "-", input="replacement")
    assert _data(target) == b"replacement"


@pytest.mark.parametrize("kind", _KINDS)
def test_put_still_replaces_an_unlocked_file(tmp_path, kind):
    target = _path(_image(tmp_path, kind), kind)
    _run("put", target, "-", input="original")
    _run("put", target, "-", input="replacement")
    assert _data(target) == b"replacement"


@pytest.mark.parametrize("kind", _KINDS)
def test_cp_force_replaces_a_locked_file(tmp_path, kind):
    target = _locked_file(tmp_path, kind)
    source = _image(tmp_path, "dfs", "source")
    _run("put", f"{source}:$.F", "-", input="replacement")
    _run("cp", "-f", f"{source}:$.F", target)
    assert _data(target) == b"replacement"


@pytest.mark.parametrize("kind", _KINDS)
def test_cp_without_force_refuses_cleanly(tmp_path, kind):
    target = _locked_file(tmp_path, kind)
    source = _image(tmp_path, "dfs", "source")
    _run("put", f"{source}:$.F", "-", input="replacement")
    result = _invoke("cp", f"{source}:$.F", target)
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert _data(target) == b"original"
