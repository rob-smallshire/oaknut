"""``--access`` sets access at copy time on ``disc cp`` and ``disc put``.

The value uses ``disc chmod``'s syntax: absolute (``R/R``, ``0x19``)
replaces the access the copy would otherwise produce, and incremental
(``+/R``, ``-W``) edits it. The destination keeps what it can store —
DFS only the lock bit. See issue #58.
"""

from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.disc.mount import resolve_mount

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"


def _invoke(*args, input=None):
    return CliRunner().invoke(cli, [str(arg) for arg in args], input=input)


def _run(*args, input=None):
    result = _invoke(*args, input=input)
    assert result.exit_code == 0, (args, result.output)
    return result


def _access(compound_path: str) -> int:
    with resolve_mount(compound_path) as resolved:
        return resolved.mount.acorn_meta(resolved.path).access


@pytest.fixture
def floppy(tmp_path):
    """A DFS floppy with an unlocked G.ELITE and a locked G.LOADER."""
    filepath = tmp_path / "game.ssd"
    _run("create", filepath)
    _run("put", f"{filepath}:G.ELITE", "-", input="elite")
    _run("put", f"{filepath}:G.LOADER", "-", input="loader")
    _run("chmod", f"{filepath}:G.LOADER", "L")
    return filepath


@pytest.fixture
def server(tmp_path):
    filepath = tmp_path / "scsi0.dat"
    shutil.copy(_L3FS_DAT, filepath)
    shutil.copy(_L3FS_DSC, tmp_path / "scsi0.dsc")
    return filepath


def test_cp_absolute_access(floppy, server):
    _run("cp", f"{floppy}:G.ELITE", f"{server}:afs:$.Library.Elite", "--access", "R/R")
    assert _access(f"{server}:afs:$.Library.Elite") == 0x11


def test_cp_hex_access(floppy, server):
    _run("cp", f"{floppy}:G.ELITE", f"{server}:afs:$.Elite", "--access", "0x19")
    assert _access(f"{server}:afs:$.Elite") == 0x19


def test_cp_incremental_access_edits_the_translated_access(floppy, server):
    # Locked DFS reads as LR; adding public read gives LR/R.
    _run("cp", f"{floppy}:G.LOADER", f"{server}:afs:$.Loader", "--access", "+/R")
    assert _access(f"{server}:afs:$.Loader") == 0x19


def test_cp_incremental_removal(floppy, server):
    _run("cp", f"{floppy}:G.ELITE", f"{server}:afs:$.Elite", "--access=-W")
    assert _access(f"{server}:afs:$.Elite") == 0x01


def test_cp_recursive_applies_to_every_file(floppy, server):
    _run("cp", "-r", f"{floppy}:G", f"{server}:afs:$.EliteGame", "--access", "+/R")
    assert _access(f"{server}:afs:$.EliteGame.ELITE") == 0x13
    assert _access(f"{server}:afs:$.EliteGame.LOADER") == 0x19


def test_cp_recursive_leaves_created_directories_alone(floppy, server):
    _run("cp", "-r", f"{floppy}:G", f"{server}:afs:$.EliteGame", "--access", "R/R")
    plain = _access(f"{server}:afs:$.EliteGame")
    _run("cp", "-r", f"{floppy}:G", f"{server}:afs:$.Other")
    assert plain == _access(f"{server}:afs:$.Other")


def test_cp_wildcard_applies_to_every_match(floppy, server):
    _run("cp", f"{floppy}:G.*", f"{server}:afs:$.Library/", "--access", "R/R")
    assert _access(f"{server}:afs:$.Library.ELITE") == 0x11
    assert _access(f"{server}:afs:$.Library.LOADER") == 0x11


@pytest.mark.parametrize(("spec", "expected"), [("R/R", 0x03), ("L", 0x09), ("+L", 0x09)])
def test_cp_to_dfs_keeps_only_the_lock_bit(floppy, tmp_path, spec, expected):
    destination = tmp_path / "copy.ssd"
    _run("create", destination)
    _run("cp", f"{floppy}:G.ELITE", f"{destination}:$.ELITE", "--access", spec)
    assert _access(f"{destination}:$.ELITE") == expected


def test_cp_invalid_access_writes_nothing(floppy, server):
    result = _invoke("cp", f"{floppy}:G.ELITE", f"{server}:afs:$.Elite", "--access", "QQ/")
    assert result.exit_code != 0
    assert "Traceback" not in result.output
    with resolve_mount(f"{server}:afs:$") as resolved:
        assert not resolved.mount.exists("$.Elite")


def test_put_absolute_access(tmp_path):
    destination = tmp_path / "f.adl"
    _run("create", destination)
    _run("put", f"{destination}:$.NOTES", "-", "--access", "LR/R", input="x")
    assert _access(f"{destination}:$.NOTES") == 0x19


def test_put_incremental_access_edits_the_default(tmp_path):
    # A new ADFS file defaults to WR/R; +L locks it.
    destination = tmp_path / "f.adl"
    _run("create", destination)
    _run("put", f"{destination}:$.NOTES", "-", "--access", "+L", input="x")
    assert _access(f"{destination}:$.NOTES") == 0x1B


def test_put_access_overrides_a_sidecar(tmp_path):
    (tmp_path / "H").write_bytes(b"x")
    (tmp_path / "H.inf").write_text("$.H 00001900 00008023 00000001 33\n")
    destination = tmp_path / "f.adl"
    _run("create", destination)
    _run("put", f"{destination}:$.H", tmp_path / "H", "--access", "R/R")
    assert _access(f"{destination}:$.H") == 0x11
