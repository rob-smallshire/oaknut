"""CLI tests for the --metadata-lens option and the per-format defaults.

The lens decides how the load/exec fields are read for display: as raw
``addresses`` or as a decoded RISC OS ``type-date``. ``auto`` (the
default) follows each filing system's declared preference.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH


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


class TestEqualLoadExec:
    """RISC OS FileSwitch: a marker-bearing pair with load == exec is a plain
    address, not a datestamp. Exercised on the Arthur Welcome disc, where
    FPEmulator (&FFFFFA00/&FFFFFA00) sat next to genuinely dated modules.
    """

    _D_ARTHUR = (
        REFERENCE_IMAGES_DIRPATH / "adfs-riscos" / "D_Arthur_Welcome.adf"
    )

    def test_equal_pair_shows_addresses_dated_neighbours_keep_dates(
        self, runner: CliRunner
    ):
        out = _run(
            runner, "ls", "--as", "json", "--detailed", f"{self._D_ARTHUR}:$.Modules"
        ).output
        rows = {r["name"]: r for r in json.loads(out)["reports"]["entries"]["rows"]}
        # load == exec -> address pair, no filetype/datestamp decoded.
        fp = rows["FPEmulator"]
        assert fp["load"] == 0xFFFFFA00 and fp["exec"] == 0xFFFFFA00
        assert fp["filetype"] == "" and fp["datestamp"] == ""
        # load != exec -> a genuine 1987 datestamp is still decoded.
        assert rows["RAM_Basic"]["datestamp"]
        assert rows["RAM_Basic"]["filetype"] == 0xFFA


class TestDFS:
    """DFS defaults to addresses and tolerates the lens option gracefully."""

    def test_type_date_lens_still_shows_addresses(
        self, runner: CliRunner, dfs_image_filepath: Path
    ):
        # DFS carries no filetype/datestamp, so even when the type-date lens
        # is forced there is nothing to decode and the load/exec pair must
        # still be shown — the row is never blanked.
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            "--metadata-lens", "type-date", f"{dfs_image_filepath}:$",
            env={"COLUMNS": "200"},
        ).output
        assert "Load" in out and "Exec" in out
        assert "Filetype" not in out and "Datestamp" not in out

    def test_type_date_lens_keeps_raw_load_in_json(
        self, runner: CliRunner, dfs_image_filepath: Path
    ):
        out = _run(
            runner, "ls", "--as", "json", "--detailed",
            "--metadata-lens", "type-date", f"{dfs_image_filepath}:$",
        ).output
        rows = json.loads(out)["reports"]["entries"]["rows"]
        # Every file keeps a real integer load address; nothing is concealed.
        files = [r for r in rows if r["type"] == "file"]
        assert files and all(isinstance(r["load"], int) for r in files)


class TestZip:
    """A ZIP of RISC OS files decodes filetypes by default (type-date lens)."""

    def _riscos_zip(self, tmp_path: Path) -> Path:
        archive_filepath = tmp_path / "riscos.zip"
        with zipfile.ZipFile(archive_filepath, "w") as archive:
            archive.writestr("Sprites,ff9", b"sprite data")
        return archive_filepath

    def test_default_decodes_filetype_and_conceals_address(
        self, runner: CliRunner, tmp_path: Path
    ):
        archive = self._riscos_zip(tmp_path)
        out = _run(
            runner, "ls", "--as", "display", "--detailed", str(archive),
            env={"COLUMNS": "200"},
        ).output
        assert "Sprite" in out
        assert "Filetype" in out
        assert "0xFFFFF900" not in out  # the filetyped load address is concealed

    def test_addresses_lens_reveals_raw_load(
        self, runner: CliRunner, tmp_path: Path
    ):
        archive = self._riscos_zip(tmp_path)
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            "--metadata-lens", "addresses", str(archive),
            env={"COLUMNS": "200"},
        ).output
        assert "0xFFFFF900" in out
        assert "Filetype" not in out  # the decode is suppressed under addresses


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

    def test_type_date_lens_does_not_conceal_real_addresses(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        # AFS load/exec are genuine 32-bit addresses that may land in the
        # 0xFFF00000 range that trips the filetype marker. AFS is not
        # Filetyped, so those addresses are not an encoding of a filetype and
        # must stay visible in the human view even when type-date is forced.
        image = partitioned_image_with_files
        _run(runner, "set-load", f"{image}:afs:$.afsA", "0xFFF00000")
        out = _run(
            runner, "ls", "--as", "display", "--detailed",
            "--metadata-lens", "type-date", f"{image}:afs:$",
            env={"COLUMNS": "240"},
        ).output
        # The real address is shown, not blanked out as a filetype encoding.
        assert "0xFFF00000" in out
