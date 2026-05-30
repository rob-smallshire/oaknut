"""Reusable wildcard matchers behind the :class:`WildcardMatching` capability.

Most filing systems glob by the same engine — :mod:`fnmatch` — differing
only in which characters are metacharacters: Acorn uses ``*`` and ``#``
(with ``?`` an ordinary character), the Unix default uses ``*`` and
``?``. :class:`FnmatchWildcards` captures that: it maps a filesystem's
metacharacters onto :mod:`fnmatch` and escapes every other character, so
a character that is a metacharacter elsewhere is matched literally here.

A filing system whose matching is *not* fnmatch-shaped (DOS 8.3 folding,
say) implements :class:`~oaknut.filesystem.WildcardMatching` directly
rather than reusing this.
"""

from __future__ import annotations

import fnmatch

from oaknut.filesystem.capabilities import WildcardSyntax

#: Characters :mod:`fnmatch` treats specially; escaped (as a one-member
#: set ``[x]``) when they are not metacharacters of the active syntax.
_FNMATCH_SPECIAL = frozenset("*?[]")


class FnmatchWildcards:
    """An :mod:`fnmatch`-backed :class:`WildcardMatching` implementation.

    *fnmatch_map* maps each of the syntax's metacharacters to its
    :mod:`fnmatch` equivalent (``{"*": "*", "#": "?"}`` for Acorn). Every
    character outside the map is matched literally, so an Acorn matcher
    treats a literal ``?`` as itself, not a wildcard. Matching is
    case-insensitive, the Acorn (and DOS) convention.
    """

    def __init__(self, syntax: WildcardSyntax, fnmatch_map: dict[str, str]):
        self._syntax = syntax
        self._fnmatch_map = fnmatch_map

    @property
    def wildcard_syntax(self) -> WildcardSyntax:
        return self._syntax

    def is_pattern(self, name: str) -> bool:
        return any(char in name for char in self._syntax.chars)

    def matches(self, pattern: str, name: str) -> bool:
        return fnmatch.fnmatchcase(name.upper(), self._to_fnmatch(pattern.upper()))

    def _to_fnmatch(self, pattern: str) -> str:
        out: list[str] = []
        for char in pattern:
            if char in self._fnmatch_map:
                out.append(self._fnmatch_map[char])
            elif char in _FNMATCH_SPECIAL:
                out.append(f"[{char}]")  # a literal of an fnmatch special
            else:
                out.append(char)
        return "".join(out)


#: Acorn filing-system wildcards: ``*`` any run, ``#`` one character.
ACORN_WILDCARDS = WildcardSyntax(
    (("*", "any sequence of characters"), ("#", "exactly one character"))
)

#: The CLI's default when a mount does not declare its own syntax.
UNIX_WILDCARDS = WildcardSyntax(
    (("*", "any sequence of characters"), ("?", "exactly one character"))
)

#: Ready matchers — both satisfy :class:`WildcardMatching` by duck typing.
ACORN_MATCHER = FnmatchWildcards(ACORN_WILDCARDS, {"*": "*", "#": "?"})
UNIX_MATCHER = FnmatchWildcards(UNIX_WILDCARDS, {"*": "*", "?": "?"})


class AcornWildcards:
    """Mixin giving a mount the Acorn :class:`WildcardMatching` capability.

    The Acorn filing systems (DFS, ADFS, AFS, ROMFS, and ZIPped Acorn
    files) all glob with ``*`` and ``#``, so they share one matcher
    rather than each re-deriving it.
    """

    wildcard_syntax = ACORN_WILDCARDS

    def is_pattern(self, name: str) -> bool:
        return ACORN_MATCHER.is_pattern(name)

    def matches(self, pattern: str, name: str) -> bool:
        return ACORN_MATCHER.matches(pattern, name)
