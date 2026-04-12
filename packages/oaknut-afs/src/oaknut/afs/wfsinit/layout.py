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

# Names reserved for the built-in accounts that initialise() creates
# automatically (WFSINIT.bas lines 2140-2160 and DATA at line 3930).
BUILTIN_ACCOUNT_NAMES = frozenset({"Syst", "Boot", "Welcome"})


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

    Defaults match WFSINIT's historical behaviour: the AFS region
    occupies the existing tail free extent without pre-compaction.
    Pass ``compact_adfs=True`` (and optionally
    ``size=AFSSizeSpec.max()``) to compact the ADFS partition first
    and reclaim the maximum possible space.

    The default quota matches WFSINIT's historical value of
    ``0x40404`` (~256 KiB) — kept small because the L3FS address
    encoding caps a single drive at ~512 MB and real-period
    Winchesters were ~20 MB. Callers building discs for modern
    large images can raise this explicitly.
    """

    disc_name: str
    date: datetime.date = field(default_factory=datetime.date.today)
    size: AFSSizeSpec = field(default_factory=AFSSizeSpec.existing_free)
    compact_adfs: bool = False
    addition_factor: int = 0
    default_quota: int = 0x40404
    users: Sequence[UserSpec] = ()
    libraries: Sequence[str] = ()  # names or paths passed to emplace_library
    repartition: bool = True
    omit_builtins: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.disc_name:
            raise ValueError("disc_name must not be empty")
        if len(self.disc_name) > 16:
            raise ValueError(f"disc_name exceeds 16 chars: {self.disc_name!r}")
        if self.default_quota < 0:
            raise ValueError("default_quota must be non-negative")
        # Validate omit_builtins against the known set.
        builtin_upper = {n.upper(): n for n in BUILTIN_ACCOUNT_NAMES}
        for name in self.omit_builtins:
            if name.upper() not in builtin_upper:
                raise ValueError(
                    f"omit_builtins name {name!r} is not a built-in account; "
                    f"valid names are {', '.join(sorted(BUILTIN_ACCOUNT_NAMES))}"
                )
        omitted_upper = {n.upper() for n in self.omit_builtins}
        # User-specified names must not collide with non-omitted built-ins.
        active_builtin_upper = set(builtin_upper) - omitted_upper
        names_seen: set[str] = set()
        for user in self.users:
            upper = user.name.upper()
            if upper in active_builtin_upper:
                raise ValueError(
                    f"user name {user.name!r} is reserved (built-in account); "
                    f"initialise() creates {', '.join(sorted(BUILTIN_ACCOUNT_NAMES))} automatically "
                    f"(use omit_builtins to suppress)"
                )
            if upper in names_seen:
                raise ValueError(f"duplicate user name: {user.name!r}")
            names_seen.add(upper)
