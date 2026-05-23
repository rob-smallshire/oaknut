"""Cross-filesystem :class:`Stat` protocol.

A :class:`Stat` is the shape returned by any oaknut path object's
``stat()`` method. Each filesystem family — DFS, ADFS, AFS — has its
own concrete dataclass with format-specific extras (DFS exposes
``start_sector``, ADFS exposes per-bit ``owner_read`` / ``owner_write``
/ …, AFS exposes ``sin`` and the raw on-disc ``afs_access`` byte),
but every one of them conforms to the fields below so portable code
can iterate across filesystems uniformly::

    def show(entry) -> None:
        st = entry.stat()
        kind = "dir" if st.is_directory else "file"
        print(f"{entry.name:12s} {kind} {st.length:>8d}  {st.access}")

The :class:`Stat` protocol is the documented public surface; the
per-filesystem dataclasses are implementation detail kept reachable
for callers that want their extras.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from oaknut.file.access import Access


@runtime_checkable
class Stat(Protocol):
    """Uniform metadata shape returned by every oaknut path's ``stat()``.

    Six fields, all required:

    - ``length`` — byte length of the file's contents (0 for directories).
    - ``load_address`` — Acorn load address (32-bit unsigned).
    - ``exec_address`` — Acorn exec address (32-bit unsigned).
    - ``access`` — canonical :class:`~oaknut.file.Access` flags
      synthesised from whatever the source filesystem stores natively.
    - ``is_directory`` — ``True`` if this entry is a directory.
    - ``date`` — entry date stamp, or ``None`` where the format does
      not store one. Type is the source filesystem's date type
      (AFS uses ``oaknut.afs.AfsDate``); callers that need to compare
      across filesystems should check ``is None`` first.

    ``Stat`` is decorated with :func:`typing.runtime_checkable` so
    ``isinstance(st, Stat)`` works for ducktype tests, but the cheapest
    check in cross-filesystem code is still attribute access.
    """

    length: int
    load_address: int
    exec_address: int
    access: Access
    is_directory: bool
    date: Any
