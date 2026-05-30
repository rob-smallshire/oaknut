"""ROMFS contributed ``disc`` commands.

The ``disc romfs`` command group, contributed to the CLI on the
``oaknut.command`` axis (see ``docs/dev/contributed-commands.md``). It holds
the ROMFS-specific paged-ROM *header* properties that do not fit the generic
mount model — the copyright string and the binary version byte — as simple
getters and setters on an existing image. Creating an image is the generic
``disc create``; this group only queries and tweaks header metadata.

This module imports Click and is loaded only when ``oaknut-romfs`` is
installed with its ``[cli]`` extra; the library core never imports it.
Errors raised as :class:`~oaknut.romfs.exceptions.ROMFSError` are reported
by the CLI's shared error boundary.
"""

from __future__ import annotations

from pathlib import Path

import click

_IMAGE = click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))


@click.group()
def romfs() -> None:
    """Acorn ROM Filing System administration."""


@romfs.command(name="get-copyright")
@_IMAGE
def get_copyright_command(image: Path) -> None:
    """Print the paged-ROM copyright string of IMAGE."""
    from oaknut.romfs.romfs import get_copyright

    click.echo(get_copyright(image.read_bytes()))


@romfs.command(name="set-copyright")
@_IMAGE
@click.argument("copyright")
def set_copyright_command(image: Path, copyright: str) -> None:
    """Set the paged-ROM copyright string of IMAGE (must begin "(C)").

    A same-length string is written in place. A different length moves the
    service handler, so the ROM is rebuilt — done only for a created-style
    ROM (no language entry, nothing after the filing system); other ROMs are
    refused to avoid disturbing their code.
    """
    from oaknut.romfs.romfs import set_copyright

    image.write_bytes(set_copyright(image.read_bytes(), copyright))


@romfs.command(name="get-version")
@_IMAGE
def get_version_command(image: Path) -> None:
    """Print the paged-ROM binary version byte of IMAGE."""
    from oaknut.romfs.romfs import get_version

    click.echo(get_version(image.read_bytes()))


@romfs.command(name="set-version")
@_IMAGE
@click.argument("version")
def set_version_command(image: Path, version: str) -> None:
    """Set the paged-ROM binary version byte of IMAGE (0-255).

    VERSION honours a base prefix, like the address commands: ``0x`` hex
    (e.g. ``0x80``), ``0o`` octal, ``0b`` binary, or a plain decimal value.
    """
    from oaknut.file import parse_address
    from oaknut.romfs.romfs import set_version

    image.write_bytes(set_version(image.read_bytes(), parse_address(version)))
