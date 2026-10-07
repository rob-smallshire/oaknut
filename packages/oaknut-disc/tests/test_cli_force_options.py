"""Every command that opens an image can be told how to read it (#83).

A command that opens an image accepts ``--filesystem`` / ``--geometry`` to
open it as a given filesystem when content detection rejects it. ``cp``
and ``gather``, which open several images, force each side separately with
``--source-*`` / ``--dest-*``. The not-recognised error names the option
the command actually takes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli

# Top-level commands that open no image by path, or force it their own way.
_NO_IMAGE = {
    "identify",
    "list-filesystems",
    "describe-filesystem",
    "list-reports",
    "describe-report",
    "list-report-formats",
    "describe-report-format",
    "create",
}
# Per-filesystem command groups open images with their own format's reader.
_GROUPS = {"dfs", "adfs", "afs", "romfs"}
_MULTI_IMAGE = {"cp", "gather"}


def _command_names() -> list[str]:
    seen, names = set(), []
    for name, command in sorted(cli.commands.items()):
        if name.startswith("*") or id(command) in seen:
            continue  # an Acorn alias of a command listed under its own name
        seen.add(id(command))
        names.append(name)
    return names


def _options(name: str) -> set[str]:
    return {opt for param in cli.commands[name].params for opt in getattr(param, "opts", [])}


@pytest.mark.parametrize(
    "name", [n for n in _command_names() if n not in _NO_IMAGE | _GROUPS | _MULTI_IMAGE]
)
def test_a_command_that_opens_an_image_accepts_the_force_options(name):
    assert {"--filesystem", "--geometry"} <= _options(name)


@pytest.mark.parametrize("name", sorted(_MULTI_IMAGE))
def test_a_multi_image_command_forces_each_side_separately(name):
    assert {
        "--source-filesystem",
        "--source-geometry",
        "--dest-filesystem",
        "--dest-geometry",
    } <= _options(name)


# -- Forcing opens an image detection rejects --


def _rejected_dfs(runner: CliRunner, tmp_path: Path, name: str = "odd.ssd") -> Path:
    """A real Acorn DFS disc with one file, whose title detection rejects."""
    image = tmp_path / name
    runner.invoke(cli, ["create", str(image), "--title", "T"])
    host = tmp_path / "payload"
    host.write_bytes(b"data")
    runner.invoke(cli, ["put", f"{image}:$.FILE", str(host), "--meta-format", "none"])
    raw = bytearray(image.read_bytes())
    raw[3] = 0xC1  # a top-bit title byte: not recognised as DFS
    image.write_bytes(bytes(raw))
    assert runner.invoke(cli, ["ls", str(image)]).exit_code != 0
    return image


def test_validate_with_filesystem_opens_a_rejected_image(runner, tmp_path):
    image = _rejected_dfs(runner, tmp_path)
    result = runner.invoke(cli, ["validate", "--filesystem", "acorn-dfs", str(image)])
    assert result.exit_code != 2, result.output  # not a usage error
    assert "no installed filesystem recognises" not in result.output, result.output


def test_get_with_filesystem_reads_a_rejected_image(runner, tmp_path):
    image = _rejected_dfs(runner, tmp_path)
    out = tmp_path / "out"
    result = runner.invoke(cli, ["get", "--filesystem", "acorn-dfs", f"{image}:$.FILE", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == b"data"


def test_put_with_filesystem_writes_a_rejected_image(runner, tmp_path):
    image = _rejected_dfs(runner, tmp_path)
    host = tmp_path / "more"
    host.write_bytes(b"more")
    result = runner.invoke(
        cli,
        ["put", "--filesystem", "acorn-dfs", f"{image}:$.MORE", str(host), "--meta-format", "none"],
    )
    assert result.exit_code == 0, result.output
    listing = runner.invoke(cli, ["ls", "--filesystem", "acorn-dfs", f"{image}:$"]).output
    assert "MORE" in listing


def test_cp_from_a_rejected_source(runner, tmp_path):
    source = _rejected_dfs(runner, tmp_path)
    dest = tmp_path / "dest.ssd"
    runner.invoke(cli, ["create", str(dest), "--title", "D"])
    result = runner.invoke(
        cli,
        ["cp", "--source-filesystem", "acorn-dfs", f"{source}:$.FILE", f"{dest}:$.FILE"],
    )
    assert result.exit_code == 0, result.output
    assert runner.invoke(cli, ["cat", f"{dest}:$.FILE"]).output == "data"


def test_cp_to_a_rejected_destination(runner, tmp_path):
    source = tmp_path / "source.ssd"
    runner.invoke(cli, ["create", str(source), "--title", "S"])
    host = tmp_path / "payload"
    host.write_bytes(b"data")
    runner.invoke(cli, ["put", f"{source}:$.NEW", str(host), "--meta-format", "none"])
    dest = _rejected_dfs(runner, tmp_path)
    result = runner.invoke(
        cli, ["cp", "--dest-filesystem", "acorn-dfs", f"{source}:$.NEW", f"{dest}:$.NEW"]
    )
    assert result.exit_code == 0, result.output


# -- The hint names the option the command takes --


def test_the_hint_names_filesystem_for_a_single_image_command(runner, tmp_path):
    image = _rejected_dfs(runner, tmp_path)
    result = runner.invoke(cli, ["validate", str(image)])
    assert "--filesystem" in result.output


def test_the_hint_names_the_side_for_cp(runner, tmp_path):
    source = _rejected_dfs(runner, tmp_path)
    dest = tmp_path / "dest.ssd"
    runner.invoke(cli, ["create", str(dest), "--title", "D"])
    result = runner.invoke(cli, ["cp", f"{source}:$.FILE", f"{dest}:$.FILE"])
    assert "--source-filesystem" in result.output
    assert "--dest-filesystem" not in result.output


@pytest.mark.parametrize("command", [["find"], ["for-each"]])
def test_partition_walking_commands_search_the_forced_mount(runner, tmp_path, command):
    image = _rejected_dfs(runner, tmp_path)
    args = [*command, "--filesystem", "acorn-dfs", f"{image}:$.F*"]
    if command == ["for-each"]:
        args += ["--", "echo", "{}"]
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert "FILE" in result.output
