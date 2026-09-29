"""Pin the access every copying path produces, across filing systems.

These are characterisation tests: they record what ``disc cp``,
``disc import``, ``disc put`` and :func:`oaknut.file.copy.copy_file` do
to file access today, so the conventions refactor (issue #60) can be
shown not to change behaviour, and each later behaviour change arrives
as a visible edit to an expectation here. Rows known to be wrong are
marked with the issue that will change them.
"""

from __future__ import annotations

import shutil

import pytest
from click.testing import CliRunner
from oaknut.adfs import ADFS
from oaknut.dfs import DFS
from oaknut.disc.cli import cli
from oaknut.disc.mount import resolve_mount
from oaknut.file.copy import copy_file

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"

_SUFFIX = {"dfs": "ssd", "adfs": "adl", "afs": "dat", "romfs": "rom"}


def _run(*args, input=None):
    result = CliRunner().invoke(cli, [str(arg) for arg in args], input=input)
    assert result.exit_code == 0, (args, result.output)
    return result


def _image(tmp_path, kind: str, stem: str):
    filepath = tmp_path / f"{stem}.{_SUFFIX[kind]}"
    if kind == "afs":
        shutil.copy(_L3FS_DAT, filepath)
        shutil.copy(_L3FS_DSC, filepath.with_suffix(".dsc"))
    else:
        _run("create", filepath)
    return filepath


def _inner(kind: str, leaf: str) -> str:
    return {"dfs": f"$.{leaf}", "adfs": f"$.{leaf}", "afs": f"afs:$.{leaf}", "romfs": leaf}[kind]


def _access(compound_path: str) -> int:
    with resolve_mount(compound_path) as resolved:
        return resolved.mount.acorn_meta(resolved.path).access


# (source kind, chmod applied to the source or None) ->
#     (source access, access after cp to dfs, adfs, afs, romfs)
_CP_MATRIX = {
    ("dfs", None): (0x03, {"dfs": 0x03, "adfs": 0x03, "afs": 0x03, "romfs": 0x01}),
    # A locked DFS file is read-only too: LR (&09), not LWR (#57).
    ("dfs", "L"): (0x09, {"dfs": 0x09, "adfs": 0x09, "afs": 0x09, "romfs": 0x01}),
    ("adfs", "WR/R"): (0x13, {"dfs": 0x03, "adfs": 0x13, "afs": 0x13, "romfs": 0x01}),
    ("adfs", "LWR/R"): (0x1B, {"dfs": 0x09, "adfs": 0x1B, "afs": 0x1B, "romfs": 0x01}),
    ("adfs", "WR/WR"): (0x33, {"dfs": 0x03, "adfs": 0x33, "afs": 0x33, "romfs": 0x01}),
    # AFS has no execute bit, so E is lost on the way in.
    ("adfs", "EWR/"): (0x07, {"dfs": 0x03, "adfs": 0x07, "afs": 0x03, "romfs": 0x01}),
    # ADFS E without R is run-only, which ROMFS keeps.
    ("adfs", "E/"): (0x04, {"dfs": 0x03, "adfs": 0x04, "afs": 0x00, "romfs": 0x04}),
    ("afs", "WR/"): (0x03, {"dfs": 0x03, "adfs": 0x03, "afs": 0x03, "romfs": 0x01}),
    ("afs", "LR/R"): (0x19, {"dfs": 0x09, "adfs": 0x19, "afs": 0x19, "romfs": 0x01}),
    # An ordinary ROMFS file is readable. A run-only one (E without R) stays
    # run-only on ADFS; AFS has no execute bit, so it arrives with no access.
    ("romfs", None): (0x01, {"dfs": 0x03, "adfs": 0x01, "afs": 0x01, "romfs": 0x01}),
    ("romfs", "E"): (0x04, {"dfs": 0x03, "adfs": 0x04, "afs": 0x00, "romfs": 0x04}),
}


@pytest.mark.parametrize(("kind", "spec"), list(_CP_MATRIX), ids=lambda v: str(v))
def test_cp_access_matrix(tmp_path, kind, spec):
    source_access, by_destination = _CP_MATRIX[(kind, spec)]
    source = _image(tmp_path, kind, "source")
    source_path = f"{source}:{_inner(kind, 'F')}"
    _run("put", source_path, "-", input="data")
    if spec is not None:
        _run("chmod", source_path, spec)
    assert _access(source_path) == source_access
    for destination_kind, expected in by_destination.items():
        destination = _image(tmp_path, destination_kind, f"to-{destination_kind}")
        destination_path = f"{destination}:{_inner(destination_kind, 'F')}"
        _run("cp", source_path, destination_path)
        assert _access(destination_path) == expected, destination_kind


def test_copy_file_dfs_locked_to_adfs(tmp_path):
    # copy_file hands the translated access to ADFS write_bytes, which
    # applies it in full, so it agrees with cp: LR/ (#63).
    source = _image(tmp_path, "dfs", "source")
    _run("put", f"{source}:$.F", "-", input="x")
    _run("chmod", f"{source}:$.F", "L")
    destination = _image(tmp_path, "adfs", "destination")
    with DFS.from_file(source) as dfs, ADFS.from_file(destination) as adfs:
        copy_file(dfs.root / "$" / "F", adfs.root / "F")
    assert _access(f"{destination}:$.F") == 0x09


def test_import_without_sidecar_gives_the_default(tmp_path):
    # With no metadata source, the destination's default for a new file
    # applies: WR/R on ADFS (#63).
    host_dirpath = tmp_path / "host"
    host_dirpath.mkdir()
    (host_dirpath / "PLAIN").write_bytes(b"x")
    destination = _image(tmp_path, "adfs", "destination")
    _run("import", destination, host_dirpath)
    assert _access(f"{destination}:$.PLAIN") == 0x13


def test_put_applies_sidecar_access(tmp_path):
    # put takes the access an .inf records (#63).
    (tmp_path / "H").write_bytes(b"x")
    (tmp_path / "H.inf").write_text("$.H 00001900 00008023 00000001 33\n")
    destination = _image(tmp_path, "adfs", "destination")
    _run("put", f"{destination}:$.H", tmp_path / "H")
    assert _access(f"{destination}:$.H") == 0x33


def test_put_without_sidecar_gives_the_default(tmp_path):
    (tmp_path / "H").write_bytes(b"x")
    destination = _image(tmp_path, "adfs", "destination")
    _run("put", f"{destination}:$.H", tmp_path / "H")
    assert _access(f"{destination}:$.H") == 0x13


def test_put_replacing_a_file_keeps_its_access(tmp_path):
    destination = _image(tmp_path, "adfs", "destination")
    _run("put", f"{destination}:$.H", "-", input="one")
    _run("chmod", f"{destination}:$.H", "WR/WR")
    _run("put", f"{destination}:$.H", "-", input="two")
    assert _access(f"{destination}:$.H") == 0x33


def test_cp_from_a_member_without_access_gives_the_default(tmp_path):
    # A ZIP member with no Acorn attributes has unknown access, so the
    # destination's default applies rather than no access at all (#63).
    import zipfile

    archive = tmp_path / "plain.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("README", b"hello")
    for kind, expected in (("adfs", 0x13), ("afs", 0x03), ("dfs", 0x03)):
        destination = _image(tmp_path, kind, f"from-zip-{kind}")
        _run("cp", f"{archive}:README", f"{destination}:{_inner(kind, 'README')}")
        assert _access(f"{destination}:{_inner(kind, 'README')}") == expected, kind
