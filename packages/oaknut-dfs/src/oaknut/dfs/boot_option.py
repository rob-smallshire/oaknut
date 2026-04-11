"""Boot option enum for Acorn DFS."""

from enum import IntEnum


class BootOption(IntEnum):
    """Disk boot option (*OPT 4,n).

    Controls what happens when the disk is booted.
    """

    OFF = 0  # No action
    LOAD = 1  # *LOAD $.!BOOT
    RUN = 2  # *RUN $.!BOOT
    EXEC = 3  # *EXEC $.!BOOT
