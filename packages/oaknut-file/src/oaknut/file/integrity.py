"""Directory-integrity post-conditions shared across filing systems.

Acorn filing systems look files up by name with linear, often
early-terminating, scans, so two entries sharing a name in one directory
leave one of them unreachable — catalogue corruption that surfaces later
as a mysterious "not found" (or worse) on real hardware. Every writable
filing system therefore asserts the no-duplicate-names invariant after a
directory mutation; this module expresses that check once.

What counts as "the same name" is filesystem-dependent (case folding,
codec, collation), so the equivalence is supplied by the caller as a
*key* function — in practice each filesystem's
:meth:`oaknut.filesystem.NameGrammar.name_key`. These helpers stay
ignorant of any one filesystem's rules; the key carries the policy.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable


def _identity(name: str) -> str:
    return name


def find_duplicate_names(
    names: Iterable[str], *, key: Callable[[str], str] | None = None
) -> list[str]:
    """Return the names that collide under *key*, sorted.

    Two names collide when ``key(a) == key(b)``; a colliding name is
    reported once however many times it repeats. *key* defaults to
    identity (exact match) — pass a filesystem's ``name_key`` to fold case
    or otherwise canonicalise per its rules.
    """
    canonicalise = key or _identity
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        folded = canonicalise(name)
        if folded in seen:
            duplicates.add(name)
        else:
            seen.add(folded)
    return sorted(duplicates)


def assert_no_duplicate_names(
    names: Iterable[str], *, where: str = "directory", key: Callable[[str], str] | None = None
) -> None:
    """Assert no two names collide under *key* (a post-condition backstop).

    Raises ``AssertionError`` naming the offending entries and *where* they
    were found, so a corrupting write fails loudly at its source rather
    than producing a silently-unreachable file. *key* carries the
    filesystem's name-equivalence rule (see :func:`find_duplicate_names`).
    """
    duplicates = find_duplicate_names(names, key=key)
    assert not duplicates, f"{where} has duplicate entries: {duplicates}"
