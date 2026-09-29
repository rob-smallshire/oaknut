"""DFS I/O-processor addresses survive copies to 32-bit filing systems.

A DFS address with both high bits set is an I/O-processor (host) address,
which OSFILE returns as ``&FFFFxxxx``. Copied to AFS or ADFS it must stay
``&FFFFxxxx``: ``&0003xxxx`` or ``&00FFxxxx`` is a parasite address, so a
binary meant for the I/O processor runs on the Second Processor instead.
The values below are the ``G.ELTS*`` catalogue entries from Mark Moxon's
Elite over Econet installation disc (issue #61). On DFS itself the human
display stays at the three bytes ``*INFO`` prints.
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

# name: (raw 18-bit load, raw 18-bit exec, expected 32-bit load, exec)
_FILES = {
    "ELTSA": (0x32000, 0x32000, 0xFFFF2000, 0xFFFF2000),
    "ELTSE": (0x31FDC, 0x32085, 0xFFFF1FDC, 0xFFFF2085),
    "ELTSI": (0x32400, 0x32C89, 0xFFFF2400, 0xFFFF2C89),
    "ELTSP": (0x01000, 0x010D1, 0x00001000, 0x000010D1),  # a parasite address
}


def _run(*args, input=None):
    result = CliRunner().invoke(cli, list(args), input=input)
    assert result.exit_code == 0, result.output
    return result


@pytest.fixture
def game_dsd(tmp_path):
    filepath = tmp_path / "game.dsd"
    _run("create", str(filepath))
    for name, (load, exec_, _, _) in _FILES.items():
        _run(
            "put",
            f"{filepath}::0.G.{name}",
            "-",
            "--load",
            hex(load),
            "--exec",
            hex(exec_),
            input=name,
        )
    return filepath


@pytest.fixture
def server_dat(tmp_path):
    filepath = tmp_path / "scsi0.dat"
    shutil.copy(_L3FS_DAT, filepath)
    shutil.copy(_L3FS_DSC, tmp_path / "scsi0.dsc")
    return filepath


def _meta(compound_path):
    with resolve_mount(compound_path) as resolved:
        meta = resolved.mount.acorn_meta(resolved.path)
    return meta.load_address, meta.exec_address


def test_dfs_reads_host_addresses_as_osfile_values(game_dsd):
    for name, (_, _, load, exec_) in _FILES.items():
        assert _meta(f"{game_dsd}::0.G.{name}") == (load, exec_), name


def test_cp_recursive_to_afs_keeps_io_addresses(game_dsd, server_dat):
    _run("cp", "-r", f"{game_dsd}::0.G", f"{server_dat}:afs:$.EliteGame")
    for name, (_, _, load, exec_) in _FILES.items():
        assert _meta(f"{server_dat}:afs:$.EliteGame.{name}") == (load, exec_), name


def test_cp_to_adfs_keeps_io_addresses(game_dsd, tmp_path):
    adfs_filepath = tmp_path / "floppy.adl"
    _run("create", str(adfs_filepath))
    for name, (_, _, load, exec_) in _FILES.items():
        _run("cp", f"{game_dsd}::0.G.{name}", f"{adfs_filepath}:$.{name}")
        assert _meta(f"{adfs_filepath}:$.{name}") == (load, exec_), name


def test_round_trip_through_afs_restores_the_dfs_catalogue(game_dsd, server_dat, tmp_path):
    _run("cp", f"{game_dsd}::0.G.ELTSE", f"{server_dat}:afs:$.ELTSE")
    back_filepath = tmp_path / "back.ssd"
    _run("create", str(back_filepath))
    _run("cp", f"{server_dat}:afs:$.ELTSE", f"{back_filepath}:$.ELTSE")
    assert _meta(f"{back_filepath}:$.ELTSE") == (0xFFFF1FDC, 0xFFFF2085)


def test_dfs_display_shows_the_three_bytes_info_prints(game_dsd):
    listing = _run(
        "ls", f"{game_dsd}::0.G", "--detailed", "--metadata-lens=addresses", "--as", "display"
    ).stdout
    assert "0xFF2000" in listing
    assert "0xFFFF2000" not in listing
    shown = _run("get-load", "--as", "display", f"{game_dsd}::0.G.ELTSE").stdout
    assert "0xFF1FDC" in shown


def test_dfs_machine_output_carries_the_osfile_value(game_dsd):
    tsv = _run(
        "ls", f"{game_dsd}::0.G", "--detailed", "--metadata-lens=addresses", "--as", "tsv"
    ).stdout
    assert str(0xFFFF2000) in tsv
