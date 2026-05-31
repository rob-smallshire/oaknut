"""``--no-wildcards`` lets a command address a file whose name contains
a wildcard metacharacter.

A DFS catalogue may hold ``GUARD#1`` / ``GUARD#2`` (real discs do — the
game Guardian ships them). But ``#`` is the Acorn single-character
wildcard, so the pattern ``GUARD#1`` also matches the ordinary file
``GUARD41``. With wildcards interpreted (the default) you cannot single
out the literal ``#`` file; ``--no-wildcards`` matches the name verbatim
and reaches exactly it.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.disc.cli import cli

# GUARD#1 / GUARD#2 are the names to reach; GUARD41 / GUARD42 are the
# decoys the # wildcard would also sweep up (GUARD?1, GUARD?2).
_HASH_FILES = {"GUARD#1": b"hash-one", "GUARD#2": b"hash-two"}
_DECOY_FILES = {"GUARD41": b"decoy-one", "GUARD42": b"decoy-two"}


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def source_image_filepath(tmp_path: Path) -> Path:
    """A DFS image holding both the # files and their numeric decoys."""
    image = tmp_path / "guardian.ssd"
    with DFS.create_file(image, ACORN_DFS_80T_SINGLE_SIDED, title="GUARD") as dfs:
        for name, data in {**_HASH_FILES, **_DECOY_FILES}.items():
            dfs.path(f"$.{name}").write_bytes(data)
    return image


def _names_in(image_filepath: Path) -> set[str]:
    with DFS.from_file(image_filepath) as dfs:
        return {entry.filename for entry in dfs.files}


def test_default_wildcards_also_match_the_decoy(
    runner: CliRunner, source_image_filepath: Path, tmp_path: Path
) -> None:
    """Default globbing: pattern GUARD#1 sweeps up GUARD41 too."""
    dst = tmp_path / "out.ssd"
    with DFS.create_file(dst, ACORN_DFS_80T_SINGLE_SIDED, title="OUT"):
        pass

    result = runner.invoke(cli, ["cp", f"{source_image_filepath}:$.GUARD#1", f"{dst}:$/"])

    assert result.exit_code == 0, result.output
    # The # is a single-char wildcard, so both GUARD#1 and GUARD41 copy.
    assert _names_in(dst) == {"GUARD#1", "GUARD41"}


def test_no_wildcards_reaches_only_the_literal_file(
    runner: CliRunner, source_image_filepath: Path, tmp_path: Path
) -> None:
    """--no-wildcards: GUARD#1 names exactly the file with the # byte."""
    dst = tmp_path / "out.ssd"
    with DFS.create_file(dst, ACORN_DFS_80T_SINGLE_SIDED, title="OUT"):
        pass

    result = runner.invoke(
        cli,
        ["cp", "--no-wildcards", f"{source_image_filepath}:$.GUARD#1", f"{dst}:$.GUARD#1"],
    )

    assert result.exit_code == 0, result.output
    # Only the literal #-named file lands; the decoy is left behind.
    assert _names_in(dst) == {"GUARD#1"}


def test_no_wildcards_distinguishes_the_two_hash_files(
    runner: CliRunner, source_image_filepath: Path, tmp_path: Path
) -> None:
    """GUARD#2 verbatim reaches GUARD#2, never GUARD#1 or the decoys."""
    dst = tmp_path / "out.ssd"
    with DFS.create_file(dst, ACORN_DFS_80T_SINGLE_SIDED, title="OUT"):
        pass

    result = runner.invoke(
        cli,
        ["cp", "--no-wildcards", f"{source_image_filepath}:$.GUARD#2", f"{dst}:$.GUARD#2"],
    )

    assert result.exit_code == 0, result.output
    assert _names_in(dst) == {"GUARD#2"}


def test_rm_no_wildcards_deletes_only_the_literal_file(
    runner: CliRunner, source_image_filepath: Path
) -> None:
    """The same suppression governs rm — delete GUARD#1, spare GUARD41."""
    result = runner.invoke(
        cli, ["rm", "--no-wildcards", f"{source_image_filepath}:$.GUARD#1"]
    )

    assert result.exit_code == 0, result.output
    assert _names_in(source_image_filepath) == {"GUARD#2", "GUARD41", "GUARD42"}
