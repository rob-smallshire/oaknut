"""Title validation is consistent across filing systems (#80).

A title a filing system cannot store — too long, a character outside its
character set, or its terminator — is refused before anything is written,
with a clean error and the ``USAGE`` exit code (64), as for names (#78).
Nothing is silently truncated.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli
from oaknut.exception import ExitCode

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"
_L3FS_DSC = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dsc"

# kind -> (create arguments or None for the AFS fixture, path suffix, max length)
_KINDS = {
    "acorn-dfs": (["t.ssd", "--title", "OLD"], "", 12),
    "watford-dfs": (["t.ssd", "--filesystem", "watford-dfs", "--title", "OLD"], "", 10),
    "adfs-old": (["t.adl"], "", 19),
    "adfs-new": (["t.adf", "--geometry", "f"], "", 19),
    "adfs-big": (["t.adf", "--geometry", "e+"], "", 10),
    "afs": (None, "afs:", 16),
    "romfs": (["t.rom"], "", 8),  # wrapped in asterisks in a 10-character name
}


def _image(runner: CliRunner, tmp_path: Path, kind: str) -> str:
    create_args, suffix, _ = _KINDS[kind]
    if create_args is None:
        image = tmp_path / "t.dat"
        shutil.copy(_L3FS_DAT, image)
        shutil.copy(_L3FS_DSC, image.with_suffix(".dsc"))
    else:
        image = tmp_path / create_args[0]
        result = runner.invoke(cli, ["create", str(image), *create_args[1:]])
        assert result.exit_code == 0, result.output
    target = f"{image}:{suffix}" if suffix else str(image)
    result = runner.invoke(cli, ["title", target, "OLD"])
    assert result.exit_code == 0, result.output
    return target


def _title(runner: CliRunner, target: str) -> str:
    result = runner.invoke(cli, ["title", target])
    assert result.exit_code == 0, result.output
    return result.output.strip()


def _assert_refused(runner, target, title, message):
    result = runner.invoke(cli, ["title", target, title])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == ExitCode.USAGE, result.output
    assert message in result.output
    assert _title(runner, target) == "OLD"


@pytest.mark.parametrize("kind", list(_KINDS))
def test_a_title_too_long_is_refused(runner, tmp_path, kind):
    target = _image(runner, tmp_path, kind)
    _assert_refused(runner, target, "T" * 40, "too long")


@pytest.mark.parametrize("kind", list(_KINDS))
def test_an_unencodable_title_is_refused(runner, tmp_path, kind):
    target = _image(runner, tmp_path, kind)
    _assert_refused(runner, target, "Ā", "Ā")


@pytest.mark.parametrize("kind", ["adfs-old", "adfs-new"])
def test_the_adfs_terminator_is_refused(runner, tmp_path, kind):
    target = _image(runner, tmp_path, kind)
    _assert_refused(runner, target, "A\rB", "terminator")


@pytest.mark.parametrize("kind", list(_KINDS))
def test_a_title_at_the_maximum_length_round_trips(runner, tmp_path, kind):
    target = _image(runner, tmp_path, kind)
    max_length = _KINDS[kind][2]
    title = "T" * max_length
    result = runner.invoke(cli, ["title", target, title])
    assert result.exit_code == 0, result.output
    assert _title(runner, target) == title


# -- disc create --title follows the same rules --

_CREATE = {
    "acorn-dfs": ["c.ssd"],
    "watford-dfs": ["c.ssd", "--filesystem", "watford-dfs"],
    "adfs-old": ["c.adl"],
    "adfs-new": ["c.adf", "--geometry", "f"],
    "adfs-big": ["c.adf", "--geometry", "e+"],
    "romfs": ["c.rom"],
}


@pytest.mark.parametrize("kind", list(_CREATE))
@pytest.mark.parametrize(("title", "message"), [("T" * 40, "too long"), ("Ā", "Ā")])
def test_create_refuses_an_unstorable_title_and_writes_nothing(
    runner, tmp_path, kind, title, message
):
    filename, *options = _CREATE[kind]
    result = runner.invoke(cli, ["create", str(tmp_path / filename), *options, "--title", title])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == ExitCode.USAGE, result.output
    assert message in result.output
    assert list(tmp_path.iterdir()) == []


def test_create_refuses_an_unstorable_hard_disc_title_and_writes_nothing(runner, tmp_path):
    result = runner.invoke(
        cli, ["create", str(tmp_path / "h.dat"), "--geometry", "capacity=10MB", "--title", "Ā"]
    )
    assert result.exit_code == ExitCode.USAGE, result.output
    assert list(tmp_path.iterdir()) == []
