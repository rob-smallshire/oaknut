"""Phase 21 — CLI smoke tests.

Drives the argparse entry point with in-memory image paths and
captures stdout / stderr. These are lightweight smoke tests: they
verify each subcommand's argument parsing and main flow without
exhaustively re-proving the underlying APIs they delegate to.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from oaknut.adfs import ADFS, ADFS_L
from oaknut.afs.cli import main
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, initialise


@pytest.fixture
def disc_filepath(tmp_path: Path) -> Path:
    """Create an ADFS-L image with an initialised AFS region."""
    target_filepath = tmp_path / "scsi0.adl"
    with ADFS.create_file(target_filepath, ADFS_L) as _adfs:
        pass  # writes and flushes the blank image
    with ADFS.from_file(target_filepath, mode="r+b") as adfs:
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="CliTest",
                size=AFSSizeSpec.cylinders(20),
                users=[],
            ),
        )
    return target_filepath


class TestInfoCommand:
    def test_info_prints_disc_name(self, disc_filepath: Path, capsys) -> None:
        rc = main(["info", str(disc_filepath)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "CliTest" in out
        assert "Syst" in out


class TestLsCommand:
    def test_ls_root_shows_passwords(self, disc_filepath: Path, capsys) -> None:
        rc = main(["ls", str(disc_filepath)])
        assert rc == 0
        assert "Passwords" in capsys.readouterr().out

    def test_ls_with_explicit_path(self, disc_filepath: Path, capsys) -> None:
        rc = main(["ls", str(disc_filepath), "$"])
        assert rc == 0


class TestPutAndCat:
    def test_put_then_cat_round_trip(
        self, disc_filepath: Path, tmp_path: Path, capsysbinary
    ) -> None:
        payload = b"hello cli"
        src = tmp_path / "payload.bin"
        src.write_bytes(payload)

        rc = main(["put", str(disc_filepath), "$.Greeting", str(src)])
        assert rc == 0

        rc = main(["cat", str(disc_filepath), "$.Greeting"])
        assert rc == 0
        captured = capsysbinary.readouterr().out
        assert captured == payload


class TestInitialiseCommand:
    def test_initialise_from_scratch(self, tmp_path: Path) -> None:
        target_filepath = tmp_path / "fresh.adl"
        with ADFS.create_file(target_filepath, ADFS_L) as _adfs:
            pass
        rc = main(
            [
                "initialise",
                str(target_filepath),
                "--disc-name",
                "FromCli",
                "--cylinders",
                "10",
                "--user",
                "bob",
            ]
        )
        assert rc == 0

        with ADFS.from_file(target_filepath) as adfs:
            afs = adfs.afs_partition
            assert afs.disc_name == "FromCli"
            names = {u.name for u in afs.users.active}
            assert names == {"Syst", "Boot", "Welcome", "bob"}
            assert afs.users.find("Syst").is_system
