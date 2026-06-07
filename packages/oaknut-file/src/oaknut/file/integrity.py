"""Directory-integrity post-conditions shared across filing systems.

Acorn filing systems look files up by name with linear, often
early-terminating, scans, so two entries sharing a name in one directory
leave one of them unreachable — catalogue corruption that surfaces later
as a mysterious "not found" (or worse) on real hardware. Every writable
filing system therefore asserts the no-duplicate-names invariant after a
directory mutation; this module expresses that check once.

Acorn names are case-insensitive, so the check folds case by default.
"""

from __future__ import annotations

from collections.abc import Iterable


def find_duplicate_names(names: Iterable[str], *, case_insensitive: bool = True) -> list[str]:
    """Return the names that occur more than once, sorted.

    A name is reported once however many times it repeats. With
    *case_insensitive* (the Acorn default) ``HELLO`` and ``hello`` collide.
    """
    seen: set[str] = set()
    duplicates: set[str] = set()
    for name in names:
        key = name.upper() if case_insensitive else name
        if key in seen:
            duplicates.add(name)
        else:
            seen.add(key)
    return sorted(duplicates)


def assert_no_duplicate_names(
    names: Iterable[str], *, where: str = "directory", case_insensitive: bool = True
) -> None:
    """Assert no name repeats in *names* (a post-condition backstop).

    Raises ``AssertionError`` naming the offending entries and *where* they
    were found, so a corrupting write fails loudly at its source rather
    than producing a silently-unreachable file.
    """
    duplicates = find_duplicate_names(names, case_insensitive=case_insensitive)
    assert not duplicates, f"{where} has duplicate entries: {duplicates}"
