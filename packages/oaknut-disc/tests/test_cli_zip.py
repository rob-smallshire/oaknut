"""CLI browse of a ZIP archive — ZIP is a filesystem on the oaknut.filesystem axis.

A ZIP member may carry a filetype (from a ``,xxx`` filename suffix) but
no access bits, so its recovered metadata has ``access=None``. These
tests pin that the listing/stat/copy commands tolerate that rather than
crashing on ``Access(None)``.
"""

import zipfile

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _filetype_zip(tmp_path):
    archive_filepath = tmp_path / "riscos.zip"
    with zipfile.ZipFile(archive_filepath, "w") as archive:
        archive.writestr("Sprites,ff9", b"sprite data")  # filetype, no access bits
        archive.writestr("Docs/ReadMe,fff", b"hello")
    return archive_filepath


class TestBrowseZip:
    def test_identifies_as_zip(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["identify", str(_filetype_zip(tmp_path))])
        assert result.exit_code == 0
        assert "zip" in result.output

    def test_ls_tolerates_absent_access_bits(self, runner: CliRunner, tmp_path):
        # Regression: a filetype-only member has access=None; ls must not
        # blow up building the Attr column.
        result = runner.invoke(cli, ["ls", str(_filetype_zip(tmp_path))])
        assert result.exit_code == 0, result.output
        assert "Sprites" in result.output
        assert "Docs" in result.output  # the synthesised directory

    def test_ls_descends_into_synthesised_directory(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["ls", f"{_filetype_zip(tmp_path)}:Docs"])
        assert result.exit_code == 0, result.output
        assert "ReadMe" in result.output

    def test_stat_tolerates_absent_access_bits(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["stat", f"{_filetype_zip(tmp_path)}:Sprites"])
        assert result.exit_code == 0, result.output

    def test_get_writes_member_and_metadata_sidecar(self, runner: CliRunner, tmp_path):
        zip_filepath = _filetype_zip(tmp_path)
        out = tmp_path / "Sprites"
        result = runner.invoke(cli, ["get", f"{zip_filepath}:Sprites", str(out)])
        assert result.exit_code == 0, result.output
        assert out.read_bytes() == b"sprite data"
        # The filetype is preserved in the .inf sidecar's load address.
        assert "FFFFF900" in out.with_suffix(".inf").read_text().upper()


class TestReadOnlyRefusal:
    """Mutating commands refuse cleanly — a clear message and a non-zero,
    "not permitted" exit code, never a traceback."""

    def _refuses(self, result) -> None:
        assert result.exit_code != 0
        assert "read-only" in result.output.lower()
        # A clean refusal, not a crash: no traceback leaked through.
        assert "Traceback" not in result.output

    def test_put_refused(self, runner: CliRunner, tmp_path):
        host = tmp_path / "h.txt"
        host.write_text("data")
        result = runner.invoke(cli, ["put", f"{_filetype_zip(tmp_path)}:New", str(host)])
        self._refuses(result)

    def test_rm_refused(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["rm", f"{_filetype_zip(tmp_path)}:Sprites"])
        self._refuses(result)

    def test_mv_refused(self, runner: CliRunner, tmp_path):
        z = _filetype_zip(tmp_path)
        result = runner.invoke(cli, ["mv", f"{z}:Sprites", f"{z}:Other"])
        self._refuses(result)

    def test_set_load_refused(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["set-load", f"{_filetype_zip(tmp_path)}:Sprites", "0x8000"])
        self._refuses(result)

    def test_chmod_refused_even_without_access_bits(self, runner: CliRunner, tmp_path):
        # Sprites has a filetype but no access bits (access=None); chmod must
        # reach the read-only refusal, not crash on Access(None).
        result = runner.invoke(cli, ["chmod", f"{_filetype_zip(tmp_path)}:Sprites", "WR/R"])
        self._refuses(result)
