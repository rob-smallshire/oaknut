"""Cross-filesystem cp translates filetype / datestamp through capabilities.

ADFS encodes both in the load/exec fields; AFS keeps a native date and no
filetype. A copy between them must translate, not copy raw load/exec.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _tsv_field(output: str, key: str) -> str:
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] == key:
            return parts[1]
    raise AssertionError(f"{key!r} not in {output!r}")


def _make_stamped_adfs(runner: CliRunner, tmp_path: Path) -> Path:
    from oaknut.adfs import ADFS, ADFS_L

    image = tmp_path / "src.adl"
    with ADFS.create_file(image, ADFS_L, title="Src"):
        pass
    runner.invoke(cli, ["put", f"{image}:$.SRC", "-"], input="x")
    runner.invoke(cli, ["set-filetype", f"{image}:$.SRC", "Obey"])
    runner.invoke(cli, ["set-datestamp", f"{image}:$.SRC", "2024-03-01T14:22:08"])
    return image


class TestADFSTypedToAFS:
    def test_datestamp_translated_to_native_field(
        self, runner: CliRunner, tmp_path: Path, adfs_hard_with_afs_filepath: Path
    ):
        src = _make_stamped_adfs(runner, tmp_path)
        afs = adfs_hard_with_afs_filepath
        result = runner.invoke(cli, ["cp", f"{src}:$.SRC", f"{afs}:afs:$.DST"])
        assert result.exit_code == 0, result.output
        got = runner.invoke(cli, ["get-datestamp", "--as", "display", f"{afs}:afs:$.DST"])
        assert "2024-03-01" in got.output  # native AFS date (day resolution)

    def test_encoding_not_carried_as_bogus_address(
        self, runner: CliRunner, tmp_path: Path, adfs_hard_with_afs_filepath: Path
    ):
        src = _make_stamped_adfs(runner, tmp_path)
        afs = adfs_hard_with_afs_filepath
        runner.invoke(cli, ["cp", f"{src}:$.SRC", f"{afs}:afs:$.DST"])
        stat = runner.invoke(cli, ["stat", "--as", "tsv", f"{afs}:afs:$.DST"])
        # The 0xFFF… encoding must not land in AFS's real load address field.
        assert int(_tsv_field(stat.output, "Load")) & 0xFFF00000 != 0xFFF00000


class TestAFSToADFS:
    def test_native_date_encoded_into_adfs(
        self, runner: CliRunner, tmp_path: Path, adfs_hard_with_afs_filepath: Path
    ):
        from oaknut.adfs import ADFS, ADFS_L

        afs = adfs_hard_with_afs_filepath
        runner.invoke(cli, ["put", f"{afs}:afs:$.AF", "-"], input="y")
        runner.invoke(cli, ["set-datestamp", f"{afs}:afs:$.AF", "2005-06-15T00:00:00"])
        dst = tmp_path / "dst.adl"
        with ADFS.create_file(dst, ADFS_L, title="Dst"):
            pass
        result = runner.invoke(cli, ["cp", f"{afs}:afs:$.AF", f"{dst}:$.GOT"])
        assert result.exit_code == 0, result.output
        # The date survives, encoded into the ADFS load/exec fields.
        got = runner.invoke(cli, ["get-datestamp", "--as", "display", f"{dst}:$.GOT"])
        assert "2005-06-15" in got.output


class TestSameFilesystemUnaffected:
    def test_adfs_to_adfs_preserves_type_and_date(
        self, runner: CliRunner, tmp_path: Path
    ):
        from oaknut.adfs import ADFS, ADFS_L

        src = _make_stamped_adfs(runner, tmp_path)
        dst = tmp_path / "dst.adl"
        with ADFS.create_file(dst, ADFS_L, title="Dst"):
            pass
        result = runner.invoke(cli, ["cp", f"{src}:$.SRC", f"{dst}:$.GOT"])
        assert result.exit_code == 0, result.output
        ft = runner.invoke(cli, ["get-filetype", "--as", "display", f"{dst}:$.GOT"])
        assert "Obey" in ft.output
        ds = runner.invoke(cli, ["get-datestamp", "--as", "display", f"{dst}:$.GOT"])
        assert "2024-03-01T14:22:08" in ds.output

    def test_adfs_addressed_file_keeps_load_exec(
        self, runner: CliRunner, tmp_path: Path
    ):
        from oaknut.adfs import ADFS, ADFS_L

        src = tmp_path / "src.adl"
        with ADFS.create_file(src, ADFS_L, title="Src"):
            pass
        runner.invoke(cli, ["put", f"{src}:$.PROG", "-", "--load", "0x8000"], input="z")
        dst = tmp_path / "dst.adl"
        with ADFS.create_file(dst, ADFS_L, title="Dst"):
            pass
        runner.invoke(cli, ["cp", f"{src}:$.PROG", f"{dst}:$.PROG"])
        stat = runner.invoke(cli, ["stat", "--as", "tsv", f"{dst}:$.PROG"])
        # An un-dated, un-typed file keeps its real load address.
        assert int(_tsv_field(stat.output, "Load")) == 0x8000
