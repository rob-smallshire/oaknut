"""Shared CLI toolkit for the oaknut family.

This package sits *below* the filesystem packages (oaknut-dfs/adfs/afs)
so that both the ``disc`` CLI (``oaknut-disc``) and a filesystem's own
contributed commands can depend on it without a cycle — ``oaknut-disc``
depends on the filesystem packages, so they must never depend on it.

It provides:

- the **contributed-command axis** — discovery of Click commands
  registered by filesystem packages on the ``oaknut.command`` entry-point
  namespace (see :func:`contributed_commands`); and
- report-rendering helpers shared between the generic ``disc`` commands
  and the contributed ones.

See ``docs/dev/contributed-commands.md`` for the design.
"""

from __future__ import annotations

from oaknut.cli.commands import (
    COMMAND_KIND,
    COMMAND_NAMESPACE,
    contributed_commands,
)
from oaknut.cli.help import (
    PlainHelpFormatter,
    strip_rst,
    use_plain_help,
)
from oaknut.cli.reports import (
    SECTOR_SIZE,
    address_cell,
    bytes_cell,
    control_pictures,
    datestamp_cell,
    filetype_cell,
    kv_table,
    size_cell,
    text_cell,
)

__version__ = "12.14.0"

__all__ = [
    "COMMAND_KIND",
    "COMMAND_NAMESPACE",
    "contributed_commands",
    "PlainHelpFormatter",
    "strip_rst",
    "use_plain_help",
    "SECTOR_SIZE",
    "address_cell",
    "bytes_cell",
    "control_pictures",
    "datestamp_cell",
    "filetype_cell",
    "kv_table",
    "size_cell",
    "text_cell",
]
