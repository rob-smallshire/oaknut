"""The contributed-command axis.

A filesystem package contributes admin subcommands to the ``disc`` CLI by
registering a Click command (or group) on the ``oaknut.command``
entry-point namespace::

    [project.entry-points."oaknut.command"]
    afs = "oaknut.afs.cli:afs"   # afs is a click.Group

:func:`contributed_commands` discovers them; the ``disc`` root group
attaches each with ``cli.add_command(...)``. An install sees exactly the
commands its installed filesystems contribute.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import stevedore
from oaknut.extension import namespace_for

if TYPE_CHECKING:
    import click

#: The extension *kind* (axis) contributed CLI commands belong to.
COMMAND_KIND = "command"

#: The entry-point namespace commands register under: ``"oaknut.command"``.
COMMAND_NAMESPACE = namespace_for(COMMAND_KIND)


def _skip_unloadable(manager, entrypoint, exception) -> None:
    """Ignore a command whose package cannot be imported.

    A filesystem installed without its optional ``[cli]`` extra (so Click
    is absent) leaves its command entry point unloadable. That command is
    simply unavailable — not a fatal error — so the CLI degrades
    gracefully rather than crashing.
    """


def contributed_commands() -> list["click.Command"]:
    """Every Click command contributed on the ``oaknut.command`` axis.

    Each entry point's target is a ready-made Click ``Command`` or
    ``Group`` object. Returned sorted by name so the CLI's command
    listing is deterministic regardless of discovery order.
    """
    manager = stevedore.ExtensionManager(
        namespace=COMMAND_NAMESPACE,
        invoke_on_load=False,
        on_load_failure_callback=_skip_unloadable,
    )
    commands = [extension.plugin for extension in manager]
    return sorted(commands, key=lambda command: getattr(command, "name", "") or "")
