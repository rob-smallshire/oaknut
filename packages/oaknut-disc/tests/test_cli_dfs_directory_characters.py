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
