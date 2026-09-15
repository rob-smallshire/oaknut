"""Tests for ``disc gather`` — collate many disc images into one.

Driven against the real magazine cover-disc fixtures (DFS ``.ssd`` and
ADFS ``.adl``) so the cross-filesystem paths are exercised end to end.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc import gather
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_MAGAZINES = REFERENCE_IMAGES_DIRPATH / "magazines"
_MU01 = _MAGAZINES / "micro-user" / "D-MU05_01.ssd"  # DFS, title "MU05_11"
_AAB01 = _MAGAZINES / "a-and-b" / "aab-01.ssd"  # DFS, title "COLOUR_IKON"
_TAU85 = _MAGAZINES / "acorn-user" / "Tau85-a.adl"  # ADFS, title "TAU-85-1-A"


def _make_dest(runner: CliRunner, path: Path, capacity: str = "5MB") -> None:
    result = runner.invoke(cli, ["create", str(path), "--geometry", f"capacity={capacity}"])
    assert result.exit_code == 0, result.output


class TestGatherCli:
    def test_stem_names_directories_from_filenames(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        result = runner.invoke(cli, ["gather", str(dest), str(_MU01), str(_AAB01), str(_TAU85)])
        assert result.exit_code == 0, result.output

        top = runner.invoke(cli, ["ls", f"{dest}:$"]).output
        assert "D-MU05_01" in top
        assert "aab-01" in top
        assert "Tau85-a" in top

    def test_files_copied_into_their_directory(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        runner.invoke(cli, ["gather", str(dest), str(_MU01)])
        # A file that exists on the source now exists under the source's dir.
        inside = runner.invoke(cli, ["ls", f"{dest}:$.D-MU05_01"])
        assert inside.exit_code == 0, inside.output
        assert "!BOOT" in inside.output

    def test_cross_filesystem_content_integrity(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        # Pick the first real file from the ADFS source and compare bytes.
        src_ls = runner.invoke(cli, ["ls", f"{_TAU85}:$"]).output
        name = next(
            line.split("\t")[0]
            for line in src_ls.splitlines()[1:]
            if line.split("\t")[1:2] == ["file"]
        )
        original = runner.invoke(cli, ["cat", f"{_TAU85}:$.{name}"]).stdout_bytes
        runner.invoke(cli, ["gather", str(dest), str(_TAU85)])
        gathered = runner.invoke(cli, ["cat", f"{dest}:$.Tau85-a.{name}"]).stdout_bytes
        assert gathered == original

    def test_name_from_title(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        result = runner.invoke(
            cli, ["gather", str(dest), "--name-from", "title", str(_MU01), str(_AAB01)]
        )
        assert result.exit_code == 0, result.output
        top = runner.invoke(cli, ["ls", f"{dest}:$"]).output
        assert "MU05_11" in top  # the on-disc title, not the filename
        assert "COLOUR_IKO" in top  # COLOUR_IKON truncated to the 10-char ADFS limit

    def test_duplicate_names_are_suffixed(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        result = runner.invoke(cli, ["gather", str(dest), str(_AAB01), str(_AAB01)])
        assert result.exit_code == 0, result.output
        top = runner.invoke(cli, ["ls", f"{dest}:$"]).output
        assert "aab-01" in top
        assert "aab-01_1" in top

    def test_into_subdirectory(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        # --into names a directory that does not yet exist; gather creates it.
        result = runner.invoke(cli, ["gather", str(dest), "--into", "$.MAGS", str(_AAB01)])
        assert result.exit_code == 0, result.output
        assert "aab-01" in runner.invoke(cli, ["ls", f"{dest}:$.MAGS"]).output

    def test_flat_destination_refused(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "flat.ssd"
        result = runner.invoke(cli, ["create", str(dest)])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["gather", str(dest), str(_AAB01)])
        assert result.exit_code != 0
        assert "flat" in result.output.lower()

    def test_reports_source_directory_mapping(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        result = runner.invoke(cli, ["gather", str(dest), str(_MU01)])
        assert "D-MU05_01.ssd" in result.output
        assert "$.D-MU05_01" in result.output


class TestGatherApi:
    def test_returns_source_directory_pairs(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        mapping = gather(str(dest), [str(_MU01), str(_AAB01)])
        assert mapping == [(str(_MU01), "$.D-MU05_01"), (str(_AAB01), "$.aab-01")]

    def test_name_from_title_via_api(self, runner: CliRunner, tmp_path: Path) -> None:
        dest = tmp_path / "archive.dat"
        _make_dest(runner, dest)
        mapping = gather(str(dest), [str(_AAB01)], name_from="title")
        assert mapping == [(str(_AAB01), "$.COLOUR_IKO")]

    def test_flat_destination_raises(self, runner: CliRunner, tmp_path: Path) -> None:
        import click

        dest = tmp_path / "flat.ssd"
        runner.invoke(cli, ["create", str(dest)])
        with pytest.raises(click.ClickException):
            gather(str(dest), [str(_AAB01)])
