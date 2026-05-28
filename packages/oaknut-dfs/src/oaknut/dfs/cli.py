"""DFS-family contributed ``disc`` commands.

The ``disc dfs`` command group, contributed to the CLI on the
``oaknut.command`` axis (see ``docs/dev/contributed-commands.md``). It
holds the DFS-specific administration that does not fit the generic mount
model — currently ``disc dfs expand``.

This module imports Click and is loaded only when ``oaknut-dfs`` is
installed with its ``[cli]`` extra; the DFS library core never imports it.
"""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def dfs() -> None:
    """Acorn DFS / Watford DFS administration."""


@dfs.command()
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["ssd", "dsd"], case_sensitive=False),
    default=None,
    help="Target disc format. Inferred from file extension if omitted.",
)
def expand(image: Path, fmt: str | None) -> None:
    """Expand a truncated disc image to its canonical format size.

    Truncated images (e.g. produced by BeebAsm) omit trailing empty
    sectors.  This command appends zero bytes to bring the file up to
    the full format size.
    """
    from oaknut.dfs.dfs import expand as dfs_expand
    from oaknut.dfs.formats import (
        ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
        ACORN_DFS_80T_SINGLE_SIDED,
    )

    if fmt is None:
        ext = image.suffix.lower()
        if ext == ".ssd":
            fmt = "ssd"
        elif ext == ".dsd":
            fmt = "dsd"
        else:
            raise click.ClickException(
                f"Cannot infer format from extension '{image.suffix}'. "
                f"Use --format to specify ssd or dsd."
            )

    disc_format = (
        ACORN_DFS_80T_SINGLE_SIDED if fmt == "ssd" else ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED
    )

    try:
        dfs_expand(image, disc_format)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
