"""CLI tests for filetype / datestamp display and the get/set verbs."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args):
    result = runner.invoke(cli, list(args))
    return result


class TestADFSVerbs:
    def test_set_get_filetype_round_trips(self, runner: CliRunner, adfs_image_filepath: Path):
        assert _run(runner, "set-filetype", f"{adfs_image_filepath}:$.Hello", "Text").exit_code == 0
        got = _run(runner, "get-filetype", "--as", "display", f"{adfs_image_filepath}:$.Hello")
        assert got.exit_code == 0, got.output
        assert "Text" in got.output

    def test_set_get_datestamp_round_trips(self, runner: CliRunner, adfs_image_filepath: Path):
        assert (
            _run(
                runner,
                "set-datestamp",
                f"{adfs_image_filepath}:$.Hello",
                "2024-03-01T14:22:08",
            ).exit_code
            == 0
        )
        got = _run(runner, "get-datestamp", "--as", "display", f"{adfs_image_filepath}:$.Hello")
        assert got.exit_code == 0, got.output
        assert "2024-03-01T14:22:08" in got.output

    def test_get_filetype_untyped_file(self, runner: CliRunner, adfs_image_filepath: Path):
        got = _run(runner, "get-filetype", "--as", "display", f"{adfs_image_filepath}:$.Hello")
        assert got.exit_code == 0
        assert "untyped" in got.output


class TestADFSDisplay:
    def _stamp(self, runner, image):
        _run(runner, "set-filetype", f"{image}:$.Hello", "Text")
        _run(runner, "set-datestamp", f"{image}:$.Hello", "2024-03-01T14:22:08")

    def test_ls_shows_type_and_date_and_conceals_addresses(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "ls", "--as", "display", "--detailed", f"{adfs_image_filepath}:$"
        ).output
        assert "Text" in out
        assert "2024-03-01T14:22:08" in out
        # The stamped load/exec (0xFFF…) are concealed from the human table.
        assert "0xFFF" not in out

    def test_json_keeps_raw_load_and_numeric_filetype(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "ls", "--as", "json", "--detailed", f"{adfs_image_filepath}:$"
        ).output
        rows = json.loads(out)["reports"]["entries"]["rows"]
        hello = next(r for r in rows if r["name"] == "Hello")
        # Machine output stays faithful: raw load int and numeric filetype.
        assert isinstance(hello["load"], int)
        assert hello["load"] & 0xFFF00000 == 0xFFF00000
        assert hello["filetype"] == 0xFFF

    def test_stat_shows_filetype_and_datestamp(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = _run(
            runner, "stat", "--as", "display", f"{adfs_image_filepath}:$.Hello"
        ).output
        assert "Text" in out
        assert "2024-03-01T14:22:08" in out


class TestPutOverrides:
    def test_put_filetype(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            ["put", f"{adfs_image_filepath}:$.NEW", "-", "--filetype", "Obey"],
            input="data",
        )
        assert result.exit_code == 0, result.output
        got = _run(runner, "get-filetype", "--as", "display", f"{adfs_image_filepath}:$.NEW")
        assert "Obey" in got.output

    def test_put_datestamp(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            ["put", f"{adfs_image_filepath}:$.NEW", "-", "--datestamp", "2024-03-01T14:22:08"],
            input="data",
        )
        assert result.exit_code == 0, result.output
        got = _run(runner, "get-datestamp", "--as", "display", f"{adfs_image_filepath}:$.NEW")
        assert "2024-03-01T14:22:08" in got.output

    def test_put_filetype_conflicts_with_load(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        result = runner.invoke(
            cli,
            ["put", f"{adfs_image_filepath}:$.NEW", "-", "--filetype", "Text", "--load", "0x1900"],
            input="data",
        )
        assert result.exit_code != 0
        assert "cannot be combined" in result.output

    def test_put_filetype_on_dfs_errors(self, runner: CliRunner, dfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            ["put", f"{dfs_image_filepath}:$.NEW", "-", "--filetype", "Text"],
            input="data",
        )
        assert result.exit_code != 0
        assert "filetype" in result.output


class TestImportOverrides:
    def _host_tree(self, tmp_path: Path) -> Path:
        host = tmp_path / "host"
        host.mkdir()
        (host / "ONE").write_bytes(b"one")
        (host / "TWO").write_bytes(b"two")
        return host

    def test_import_datestamp_applies_to_all(
        self, runner: CliRunner, tmp_path: Path
    ):
        from oaknut.adfs import ADFS, ADFS_L

        image = tmp_path / "imp.adl"
        with ADFS.create_file(image, ADFS_L, title="Imp"):
            pass
        host = self._host_tree(tmp_path)
        result = runner.invoke(
            cli, ["import", str(image), str(host), "--datestamp", "2024-03-01T14:22:08"]
        )
        assert result.exit_code == 0, result.output
        for name in ("ONE", "TWO"):
            got = _run(runner, "get-datestamp", "--as", "display", f"{image}:$.{name}")
            assert "2024-03-01" in got.output, name

    def test_import_filetype_on_dfs_fails_fast(
        self, runner: CliRunner, tmp_path: Path
    ):
        from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS

        image = tmp_path / "imp.ssd"
        with DFS.create_file(image, ACORN_DFS_80T_SINGLE_SIDED, title="Imp"):
            pass
        host = self._host_tree(tmp_path)
        result = runner.invoke(cli, ["import", str(image), str(host), "--filetype", "Text"])
        assert result.exit_code != 0
        assert "filetype" in result.output


class TestEmptyColumnOmission:
    def test_dfs_display_drops_filetype_and_datestamp(
        self, runner: CliRunner, dfs_image_filepath: Path
    ):
        out = _run(
            runner, "ls", "--as", "display", "--detailed", f"{dfs_image_filepath}:$"
        ).output
        # DFS has neither capability, so both columns are empty for the whole
        # listing and vanish from the human table.
        assert "Filetype" not in out
        assert "Datestamp" not in out
        # Load/exec are real on DFS, so they stay.
        assert "Load" in out

    def test_tsv_keeps_columns_for_stable_schema(
        self, runner: CliRunner, dfs_image_filepath: Path
    ):
        header = _run(
            runner, "ls", "--as", "tsv", "--detailed", f"{dfs_image_filepath}:$"
        ).output.splitlines()[0]
        assert "Filetype" in header and "Datestamp" in header

    def test_adfs_all_typed_listing_drops_load_exec(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        # Make the one file in a fresh ADFS image typed+dated, so the whole
        # listing has no real load/exec.
        image = adfs_image_filepath
        # Remove the fixture's plain files, leave a single typed one.
        _run(runner, "set-filetype", f"{image}:$.Hello", "Obey")
        _run(runner, "set-datestamp", f"{image}:$.Hello", "2024-03-01T14:22:08")
        _run(runner, "rm", f"{image}:$.Games", "-r")
        out = _run(runner, "ls", "--as", "display", "--detailed", f"{image}:$").output
        assert "Filetype" in out and "Datestamp" in out
        assert "Load" not in out and "Exec" not in out


class TestUnsupportedFilesystems:
    def test_dfs_set_filetype_errors_cleanly(self, runner: CliRunner, dfs_image_filepath: Path):
        result = _run(runner, "set-filetype", f"{dfs_image_filepath}:$.Hello", "Text")
        assert result.exit_code != 0
        assert "filetype" in result.output

    def test_dfs_get_datestamp_errors_cleanly(self, runner: CliRunner, dfs_image_filepath: Path):
        result = _run(runner, "get-datestamp", f"{dfs_image_filepath}:$.Hello")
        assert result.exit_code != 0
        assert "datestamp" in result.output


class TestAFS:
    # A linear hard-disc image: its AFS partition is a writable window
    # (an interleaved floppy partition is not).
    def test_set_get_datestamp_date_only(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        image = partitioned_image_with_files
        assert (
            _run(
                runner, "set-datestamp", f"{image}:afs:$.afsA", "2005-06-15T14:30:00"
            ).exit_code
            == 0
        )
        got = _run(runner, "get-datestamp", "--as", "display", f"{image}:afs:$.afsA")
        assert got.exit_code == 0, got.output
        assert "2005-06-15" in got.output
        # Day resolution: the time of day is not part of the rendering.
        assert "14:30" not in got.output

    def test_set_filetype_errors_cleanly(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        result = _run(
            runner, "set-filetype", f"{partitioned_image_with_files}:afs:$.afsA", "Text"
        )
        assert result.exit_code != 0
        assert "filetype" in result.output

    def test_ls_shows_datestamp_and_keeps_addresses(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        image = partitioned_image_with_files
        _run(runner, "set-datestamp", f"{image}:afs:$.afsA", "2005-06-15T14:30:00")
        # Widen the terminal so the load/exec/datestamp columns are not
        # truncated to fit (AFS keeps all three).
        out = runner.invoke(
            cli,
            ["ls", "--as", "display", "--detailed", f"{image}:afs:$"],
            env={"COLUMNS": "240"},
        ).output
        assert "2005-06-15" in out
        # AFS keeps real load/exec addresses; the datestamp is a separate field.
        assert "0x" in out


class TestRawAddresses:
    """--raw-addresses shows the load/exec pair instead of decoding it."""

    def _stamp(self, runner: CliRunner, image: Path) -> None:
        _run(runner, "set-filetype", f"{image}:$.Hello", "Obey")
        _run(runner, "set-datestamp", f"{image}:$.Hello", "2024-03-01T14:22:08")

    def test_ls_raw_shows_load_exec_not_decoded(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = runner.invoke(
            cli,
            ["ls", "--as", "display", "--detailed", "--raw-addresses",
             f"{adfs_image_filepath}:$"],
            env={"COLUMNS": "200"},
        ).output
        assert "Load" in out and "Exec" in out
        assert "0xFFFFEB" in out            # the encoded load, shown as an address
        assert "Filetype" not in out        # not decoded
        assert "Datestamp" not in out
        assert "Obey" not in out

    def test_ls_default_still_decodes(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = runner.invoke(
            cli,
            ["ls", "--as", "display", "--detailed", f"{adfs_image_filepath}:$"],
            env={"COLUMNS": "200"},
        ).output
        assert "Obey" in out and "Datestamp" in out

    def test_stat_raw_shows_load_exec(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = runner.invoke(
            cli,
            ["stat", "--as", "display", "--raw-addresses", f"{adfs_image_filepath}:$.Hello"],
            env={"COLUMNS": "200"},
        ).output
        assert "Load" in out
        assert "Filetype" not in out and "Datestamp" not in out

    def test_ls_raw_tsv_empties_typed_columns(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        self._stamp(runner, adfs_image_filepath)
        out = runner.invoke(
            cli,
            ["ls", "--as", "tsv", "--detailed", "--raw-addresses", f"{adfs_image_filepath}:$"],
        ).output
        lines = out.splitlines()
        header = lines[0].lstrip("# ").split("\t")
        row = next(r.split("\t") for r in lines[1:] if r.startswith("Hello"))
        cell = dict(zip(header, row))
        assert cell["Filetype"] == "" and cell["Datestamp"] == ""
        assert int(cell["Load"]) & 0xFFF00000 == 0xFFF00000   # raw encoded load kept

    def test_env_var_sets_default(
        self, runner: CliRunner, adfs_image_filepath: Path
    ):
        # OAKNUT_DISC_RAW_ADDRESSES acts as the cross-command default.
        self._stamp(runner, adfs_image_filepath)
        out = runner.invoke(
            cli,
            ["ls", "--as", "display", "--detailed", f"{adfs_image_filepath}:$"],
            env={"COLUMNS": "200", "OAKNUT_DISC_RAW_ADDRESSES": "1"},
        ).output
        assert "Load" in out and "Exec" in out
        assert "Filetype" not in out and "Datestamp" not in out
