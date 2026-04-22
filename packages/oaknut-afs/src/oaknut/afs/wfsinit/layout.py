"""Dataclasses describing what a caller wants on a freshly-initialised disc.

``InitSpec`` captures the whole setup ``initialise()`` (phase 19)
needs: disc name, date, size, users, libraries, default quota.
``UserSpec`` describes one user.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Sequence

from oaknut.afs.exceptions import (
    AFSDiscNameError,
    AFSInitSpecError,
    AFSPasswordError,
    AFSQuotaError,
    AFSUserNameError,
)
from oaknut.afs.info_sector import _encode_disc_name
from oaknut.afs.wfsinit.partition import AFSSizeSpec
from oaknut.file import BootOption

# Names of the built-in accounts that initialise() creates
# automatically (WFSINIT.bas lines 2140-2160 and DATA at line 3930).
BUILTIN_ACCOUNT_NAMES = frozenset({"Syst", "Boot", "Welcome"})

# System-flag of each built-in: Syst is system-privileged; Boot and
# Welcome are ordinary accounts.  Callers who want to override a
# built-in via a UserSpec must match this flag to avoid silent
# contradictions (see issue #4).
_BUILTIN_IS_SYSTEM: dict[str, bool] = {
    "SYST": True,
    "BOOT": False,
    "WELCOME": False,
}

# Mirror of the limits the passwords-file encoder enforces
# (passwords.py:_LEN_USER_ID / _LEN_PASSWORD).  Kept local so
# InitSpec/UserSpec can validate eagerly without importing from the
# encoder module.
_MAX_USER_NAME_LEN = 20
_MAX_PASSWORD_LEN = 6
_MAX_QUOTA = 0xFFFFFFFF


@dataclass(frozen=True)
class UserSpec:
    """Caller-facing description of one user account to create."""

    name: str
    password: str = ""
    quota: int | None = None  # None → use InitSpec.default_quota
    system: bool = False
    privileged: bool = False
    boot: BootOption = BootOption.OFF

    def __post_init__(self) -> None:
        if not self.name:
            raise AFSUserNameError("user name must not be empty")
        try:
            encoded_name = self.name.encode("ascii")
        except UnicodeEncodeError as exc:
            raise AFSUserNameError(
                f"user name {self.name!r} must be ASCII"
            ) from exc
        if len(encoded_name) > _MAX_USER_NAME_LEN:
            raise AFSUserNameError(
                f"user name {self.name!r} exceeds "
                f"{_MAX_USER_NAME_LEN} characters"
            )
        try:
            encoded_password = self.password.encode("ascii")
        except UnicodeEncodeError as exc:
            raise AFSPasswordError(
                f"user {self.name!r}: password must be ASCII"
            ) from exc
        if len(encoded_password) > _MAX_PASSWORD_LEN:
            raise AFSPasswordError(
                f"user {self.name!r}: password exceeds "
                f"{_MAX_PASSWORD_LEN} characters"
            )
        if self.quota is not None and not (0 <= self.quota <= _MAX_QUOTA):
            raise AFSQuotaError(
                f"user {self.name!r}: quota {self.quota} outside "
                f"0..{_MAX_QUOTA:#x}"
            )


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

    Including a :class:`UserSpec` in ``users`` whose ``name`` matches
    a built-in (``Syst``, ``Boot``, or ``Welcome``) overrides that
    built-in's default quota / password / boot option.  The spec's
    ``system`` flag must match the built-in's fixed value (``True``
    for ``Syst``, ``False`` for the others); an override does not
    create a URD.  To instead reclaim a built-in's name for a fresh
    regular user (with a URD), list the name in ``omit_builtins``.
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
        # Validate disc name content eagerly — InfoSector would
        # otherwise raise deep inside initialise() after the disc
        # has already been mutated (see issue #3).
        try:
            _encode_disc_name(self.disc_name)
        except ValueError as exc:
            raise AFSDiscNameError(str(exc)) from exc
        if not (0 <= self.default_quota <= _MAX_QUOTA):
            raise AFSQuotaError(
                f"default_quota {self.default_quota} outside 0..{_MAX_QUOTA:#x}"
            )
        # Validate omit_builtins against the known set.
        builtin_upper = {n.upper(): n for n in BUILTIN_ACCOUNT_NAMES}
        for name in self.omit_builtins:
            if name.upper() not in builtin_upper:
                raise AFSInitSpecError(
                    f"omit_builtins name {name!r} is not a built-in account; "
                    f"valid names are {', '.join(sorted(BUILTIN_ACCOUNT_NAMES))}"
                )
        omitted_upper = {n.upper() for n in self.omit_builtins}
        # A user spec whose name matches a non-omitted built-in
        # overrides that built-in's default quota / password / boot
        # option (issue #4).  The system flag must match, though —
        # silently switching Syst to non-system (or Boot/Welcome to
        # system) would be a trap.
        active_builtin_upper = set(builtin_upper) - omitted_upper
        names_seen: set[str] = set()
        for user in self.users:
            upper = user.name.upper()
            if upper in active_builtin_upper:
                expected_system = _BUILTIN_IS_SYSTEM[upper]
                if user.system != expected_system:
                    canonical = builtin_upper[upper]
                    if expected_system:
                        raise AFSUserNameError(
                            f"built-in {canonical!r} is a system account; "
                            f"override must set system=True"
                        )
                    raise AFSUserNameError(
                        f"built-in {canonical!r} is not a system account; "
                        f"override must not set system=True"
                    )
            if upper in names_seen:
                raise AFSUserNameError(f"duplicate user name: {user.name!r}")
            names_seen.add(upper)
