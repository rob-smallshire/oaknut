"""WFSINIT analogues — repartition, initialise, and drive.

The sub-package holds the orchestration code that matches
``WFSINIT.bas`` at a high level, splitting the monolithic original
BASIC program into testable pieces:

- ``partition`` — flexible sizing and the partition plan / apply
  split (phase 15).
- ``layout`` — dataclasses describing what the caller wants an
  initialised disc to contain: disc name, users, library merges,
  quota, date (phase 19 data types; implementation in ``driver``).
- ``driver`` — the one-shot :func:`initialise` entry point (phase 19).

Most callers will only touch :func:`initialise` and the
:mod:`oaknut.afs.wfsinit.partition` module directly.
"""

from __future__ import annotations

from oaknut.afs.wfsinit.driver import initialise
from oaknut.afs.wfsinit.layout import BUILTIN_ACCOUNT_NAMES, InitSpec, UserSpec
from oaknut.afs.wfsinit.partition import (
    AFSSizeSpec,
    RepartitionPlan,
    apply,
    plan,
)

__all__ = [
    "AFSSizeSpec",
    "BUILTIN_ACCOUNT_NAMES",
    "InitSpec",
    "RepartitionPlan",
    "UserSpec",
    "apply",
    "initialise",
    "plan",
]
