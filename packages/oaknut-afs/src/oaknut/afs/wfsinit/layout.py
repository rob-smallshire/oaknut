"""Dataclasses describing what a caller wants on a freshly-initialised disc.

``InitSpec`` captures the whole setup ``initialise()`` (phase 19)
needs: disc name, date, size, users, libraries, default quota.
``UserSpec`` describes one user.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Sequence

from oaknut.afs.wfsinit.partition import AFSSizeSpec
from oaknut.file import BootOption


@dataclass(frozen=True)
class UserSpec:
    """Caller-facing description of one user account to create."""

    name: str
    password: str = ""
    quota: int | None = None  # None → use InitSpec.default_quota
    system: bool = False
    privileged: bool = False
    boot: BootOption = BootOption.OFF


@dataclass(frozen=True)
class InitSpec:
    """Caller-facing description of a freshly-initialised AFS disc.

    The default quota matches WFSINIT's historical value of
    ``0x40404`` (~256 KiB) — kept small because the L3FS address
    encoding caps a single drive at ~512 MB and real-period
    Winchesters were ~20 MB. Callers building discs for modern
    large images can raise this explicitly.
    """

    disc_name: str
    date: datetime.date = field(default_factory=datetime.date.today)
    size: AFSSizeSpec = field(default_factory=AFSSizeSpec.max)
    compact_adfs: bool = True
    addition_factor: int = 0
    default_quota: int = 0x40404
    users: Sequence[UserSpec] = ()
    libraries: Sequence[str] = ()  # names or paths passed to emplace_library
    repartition: bool = True

    def __post_init__(self) -> None:
        if not self.disc_name:
            raise ValueError("disc_name must not be empty")
        if len(self.disc_name) > 16:
            raise ValueError(f"disc_name exceeds 16 chars: {self.disc_name!r}")
        if self.default_quota < 0:
            raise ValueError("default_quota must be non-negative")
        names_seen: set[str] = set()
        for user in self.users:
            upper = user.name.upper()
            if upper in names_seen:
                raise ValueError(f"duplicate user name: {user.name!r}")
            names_seen.add(upper)
