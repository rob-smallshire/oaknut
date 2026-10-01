"""``disc ls`` on a DFS disc with a directory other than ``$`` or a letter (#46).

Acorn's Econet Level 1 utilities disc (in the BeebEm corpus) keeps seven
of its thirteen files under the ``&`` directory.
"""

from __future__ import annotations

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import BEEBEM_IMAGES_DIRPATH

_IMAGE_FILEPATH = BEEBEM_IMAGES_DIRPATH / "econet_level_1_utils.ssd"
_AMPERSAND_FILES = {"FS", "NOTIFY", "PROT", "PS", "REMOTE", "UNPROT", "VIEW"}


def _names(output: str) -> set[str]:
    rows = [r for r in output.splitlines() if r and not r.startswith("#")]
    return {r.split("\t")[0] for r in rows}


def test_ls_of_the_root_lists_the_ampersand_directory(runner: CliRunner):
    result = runner.invoke(cli, ["ls", "--as", "tsv", str(_IMAGE_FILEPATH)])
    assert result.exit_code == 0, result.output
    assert {"$", "&"} <= _names(result.output)


def test_ls_of_the_ampersand_directory_lists_its_files(runner: CliRunner):
    result = runner.invoke(cli, ["ls", "--as", "tsv", f"{_IMAGE_FILEPATH}:&"])
    assert result.exit_code == 0, result.output
    assert _names(result.output) == _AMPERSAND_FILES


def test_a_file_in_the_ampersand_directory_reads(runner: CliRunner):
    result = runner.invoke(cli, ["cat", f"{_IMAGE_FILEPATH}:&.PROT"])
    assert result.exit_code == 0, result.output
    assert result.output_bytes


def test_export_writes_every_file(runner: CliRunner, tmp_path):
    result = runner.invoke(cli, ["export", str(_IMAGE_FILEPATH), str(tmp_path)])
    assert result.exit_code == 0, result.output
    data_filepaths = [p for p in tmp_path.rglob("*") if p.is_file() and p.suffix != ".inf"]
    assert len(data_filepaths) == 13


# -- Copying keeps a directory DFS commands cannot create (#77) --


def _new_dfs(runner: CliRunner, tmp_path, name="copy.ssd"):
    image = tmp_path / name
    runner.invoke(cli, ["create", str(image), "--title", "T"])
    return image


def _stat(image, path):
    from oaknut.disc.mount import resolve_mount

    with resolve_mount(f"{image}:{path}") as resolved:
        meta = resolved.mount.acorn_meta(resolved.path)
        return resolved.mount.read_bytes(resolved.path), meta


def test_cp_of_a_file_keeps_its_directory(runner: CliRunner, tmp_path):
    copy = _new_dfs(runner, tmp_path)
    result = runner.invoke(cli, ["cp", f"{_IMAGE_FILEPATH}:&.PROT", f"{copy}:&.PROT"])
    assert result.exit_code == 0, result.output
    assert _stat(copy, "&.PROT") == _stat(_IMAGE_FILEPATH, "&.PROT")


def test_cp_into_the_root_lands_in_dollar_as_any_file_does(runner: CliRunner, tmp_path):
    # A single file copied into a DFS root goes to $, whatever its directory.
    copy = _new_dfs(runner, tmp_path)
    result = runner.invoke(cli, ["cp", f"{_IMAGE_FILEPATH}:&.PROT", f"{copy}:"])
    assert result.exit_code == 0, result.output
    assert _names(runner.invoke(cli, ["ls", "--as", "tsv", f"{copy}:$"]).output) == {"PROT"}


def test_cp_of_the_whole_disc_reproduces_every_file(runner: CliRunner, tmp_path):
    copy = _new_dfs(runner, tmp_path)
    result = runner.invoke(cli, ["cp", "-r", f"{_IMAGE_FILEPATH}:", f"{copy}:"])
    assert result.exit_code == 0, result.output
    listing = runner.invoke(cli, ["ls", "--as", "tsv", f"{copy}:&"]).output
    assert _names(listing) == _AMPERSAND_FILES
    assert len(_names(runner.invoke(cli, ["ls", "--as", "tsv", f"{copy}:$"]).output)) == 6


def test_cp_to_a_new_odd_directory_is_refused_cleanly(runner: CliRunner, tmp_path):
    copy = _new_dfs(runner, tmp_path)
    result = runner.invoke(cli, ["cp", f"{_IMAGE_FILEPATH}:$.FS", f"{copy}:&.FS"])
    assert result.exit_code != 0
    assert "Invalid directory '&'" in result.output
    assert isinstance(result.exception, SystemExit), result.exception


def test_put_to_an_odd_directory_is_refused_cleanly(runner: CliRunner, tmp_path):
    copy = _new_dfs(runner, tmp_path)
    host = tmp_path / "F"
    host.write_bytes(b"x")
    result = runner.invoke(cli, ["put", f"{copy}:&.F", str(host)])
    assert result.exit_code != 0
    assert "Invalid directory '&'" in result.output
    assert isinstance(result.exception, SystemExit), result.exception
