"""CLI tests for the --metadata-lens option and the per-format defaults.

The lens decides how the load/exec fields are read for display: as raw
``addresses`` or as a decoded RISC OS ``type-date``. ``auto`` (the
default) follows each filing system's declared preference.
"""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args, env=None):
    return runner.invoke(cli, list(args), env=env)


def _stamp(runner, image: Path) -> None:
    _run(runner, "set-filetype", f"{image}:$.Hello", "Obey")
    _run(runner, "set-datestamp", f"{image}:$.Hello", "2024-03-01T14:22:08")


class TestAutoFollowsFormat:
    """auto defers to the filing system's declared lens."""

    def test_riscos_disc_decodes_by_default(
        self, runner: CliRunner, adfs_typed_image_filepath: Path
    ):
        _stamp(runner, adfs_typed_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            f"{adfs_typed_image_filepath}:$", env={"COLUMNS": "200"},
        ).output
        assert "Obey" in out and "Datestamp" in out

    def test_eight_bit_adfs_shows_addresses_by_default(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        # ADFS-L (Old directories) declares the addresses lens: even a file
        # whose load/exec happen to carry the 0xFFF marker is shown as an
        # address, not decoded, unless the user asks for type-date.
        _stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            f"{adfs_image_filepath}:$", env={"COLUMNS": "200"},
        ).output
        assert "Load" in out and "Exec" in out
        assert "Obey" not in out
        assert "Filetype" not in out

    def test_dfs_shows_addresses_by_default(
        self, runner: CliRunner, dfs_image_filepath: Path
    ):
        out = _run(
            runner, "ls", "--as", "display", "--detailed", f"{dfs_image_filepath}:$"
        ).output
        assert "Load" in out
        assert "Filetype" not in out and "Datestamp" not in out


class TestExplicitOverride:
    def test_type_date_forces_decode_on_eight_bit_adfs(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        _stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            "--metadata-lens", "type-date", f"{adfs_image_filepath}:$",
            env={"COLUMNS": "200"},
        ).output
        assert "Obey" in out and "Datestamp" in out

    def test_addresses_forces_raw_on_riscos_disc(
        self, runner: CliRunner, adfs_typed_image_filepath: Path
    ):
        _stamp(runner, adfs_typed_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            "--metadata-lens", "addresses", f"{adfs_typed_image_filepath}:$",
            env={"COLUMNS": "200"},
        ).output
        assert "Load" in out and "Exec" in out
        assert "Obey" not in out

    def test_addresses_tsv_keeps_raw_load(
        self, runner: CliRunner, adfs_typed_image_filepath: Path
    ):
        _stamp(runner, adfs_typed_image_filepath)
        out = _run(
            runner, "ls", "--as", "tsv", "--detailed",
            "--metadata-lens", "addresses", f"{adfs_typed_image_filepath}:$",
        ).output
        lines = out.splitlines()
        header = lines[0].lstrip("# ").split("\t")
        row = next(r.split("\t") for r in lines[1:] if r.startswith("Hello"))
        cell = dict(zip(header, row))
        assert cell["Filetype"] == "" and cell["Datestamp"] == ""
        assert int(cell["Load"]) & 0xFFF00000 == 0xFFF00000  # raw encoded load kept

    def test_env_var_sets_default(
        self, runner: CliRunner, adfs_typed_image_filepath: Path
    ):
        _stamp(runner, adfs_typed_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            f"{adfs_typed_image_filepath}:$",
            env={"COLUMNS": "200", "OAKNUT_DISC_METADATA_LENS": "addresses"},
        ).output
        assert "Load" in out and "Exec" in out
        assert "Obey" not in out


class TestAFSDatestampIsLensIndependent:
    """AFS keeps a native datestamp, shown under either lens."""

    def test_addresses_lens_still_shows_native_datestamp(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        image = partitioned_image_with_files
        _run(runner, "set-datestamp", f"{image}:afs:$.afsA", "2005-06-15T14:30:00")
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            "--metadata-lens", "addresses", f"{image}:afs:$",
            env={"COLUMNS": "240"},
        ).output
        assert "2005-06-15" in out
        # The native date does not displace the real load/exec addresses.
        assert "0x" in out

    def test_json_afs_datestamp_present_under_addresses_lens(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        image = partitioned_image_with_files
        _run(runner, "set-datestamp", f"{image}:afs:$.afsA", "2005-06-15T14:30:00")
        out = _run(
            runner, "ls", "--as", "json", "--detailed",
            "--metadata-lens", "addresses", f"{image}:afs:$",
        ).output
        rows = json.loads(out)["reports"]["entries"]["rows"]
        afsa = next(r for r in rows if r["name"] == "afsA")
        assert afsa["datestamp"]
