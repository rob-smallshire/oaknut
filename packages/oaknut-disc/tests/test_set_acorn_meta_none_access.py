"""``set_acorn_meta`` with ``access=None`` leaves access unchanged (#66).

``None`` load and exec addresses already mean "leave alone"; access now
does too, on every mount that records Acorn metadata.
"""

from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.disc.mount import resolve_mount
from oaknut.file import AcornMeta

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"


def _run(*args, input=None):
    result = CliRunner().invoke(cli, [str(arg) for arg in args], input=input)
    assert result.exit_code == 0, (args, result.output)


def _target(tmp_path, kind: str) -> str:
    suffix = {"dfs": "ssd", "adfs": "adl", "afs": "dat", "romfs": "rom"}[kind]
    filepath = tmp_path / f"disc.{suffix}"
    if kind == "afs":
        shutil.copy(_L3FS_DAT, filepath)
        shutil.copy(_L3FS_DSC, filepath.with_suffix(".dsc"))
        return f"{filepath}:afs:$.F"
    _run("create", filepath)
    return f"{filepath}:F" if kind == "romfs" else f"{filepath}:$.F"


@pytest.mark.parametrize(
    ("kind", "spec"), [("dfs", "L"), ("adfs", "LR/R"), ("afs", "LR/R"), ("romfs", "E")]
)
def test_none_access_leaves_access_unchanged(tmp_path, kind, spec):
    target = _target(tmp_path, kind)
    _run("put", target, "-", input="x")
    _run("chmod", target, spec)
    with resolve_mount(target, writable=True) as resolved:
        before = resolved.mount.acorn_meta(resolved.path).access
        resolved.mount.set_acorn_meta(
            resolved.path, AcornMeta(load_address=0x1900, exec_address=0x8023, access=None)
        )
    with resolve_mount(target) as resolved:
        meta = resolved.mount.acorn_meta(resolved.path)
    assert meta.access == before
    assert (meta.load_address, meta.exec_address) == (0x1900, 0x8023)
