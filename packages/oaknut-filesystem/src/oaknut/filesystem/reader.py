"""Bounded, windowable raw-byte access to a disc image.

Filesystems probe and read at absolute byte offsets within a *region*
of an image. :class:`ImageReader` gives them a clamped view of one
region: reads past the end return short, never raise, and
:meth:`ImageReader.window` carves out a sub-region (an ADFS host's
reserved tail, say) as another reader sharing the same backing — so the
recursive identifier can hand each filesystem just its own slice.
"""

from __future__ import annotations

import mmap
from contextlib import suppress
from pathlib import Path
from typing import Union

ImageSource = Union["ImageReader", bytes, bytearray, memoryview, str, Path]


class ImageReader:
    """A clamped, read-only view over a region of a disc image.

    Construct via :func:`reader_for`. A reader covers ``[base, base +
    size)`` of an underlying buffer (bytes, ``memoryview`` or
    ``mmap.mmap``); all offsets passed to :meth:`read`, :meth:`find`,
    and :meth:`window` are *relative to this region*.
    """

    def __init__(
        self,
        data,
        *,
        base: int = 0,
        length: int | None = None,
        suffix: str | None = None,
        writable: bool = False,
        _closeables=(),
    ):
        self._data = data
        self._base = base
        self._length = (len(data) - base) if length is None else length
        self._suffix = suffix.lower() if suffix else None
        self._writable = writable
        self._closeables = tuple(_closeables)

    @property
    def size(self) -> int:
        """Number of bytes in this region."""
        return self._length

    @property
    def writable(self) -> bool:
        """Whether :meth:`write` (and a live :meth:`buffer`) is available.

        True when the reader is backed by writable storage (a file mapped
        for writing). Windows inherit it from their parent.
        """
        return self._writable

    @property
    def suffix(self) -> str | None:
        """The source file extension (lower-cased, with dot), if known.

        A tie-breaking *hint* for the coordinator only — never present on
        a window, and filesystems identify by content and ignore it.
        """
        return self._suffix

    def read(self, offset: int, length: int) -> bytes:
        """Return up to *length* bytes at *offset*, clamped to the region.

        Reading at or past the end yields ``b""``; a range overrunning
        the end yields only the bytes that exist.
        """
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        if offset >= self._length or length == 0:
            return b""
        end = min(offset + length, self._length)
        return bytes(self._data[self._base + offset : self._base + end])

    def write(self, offset: int, data: bytes) -> None:
        """Write *data* at region-relative *offset*, into the backing store.

        Only valid on a writable reader (see :meth:`writable`); the write
        reaches the underlying file/buffer directly. Writing past the end
        of the region is an error rather than a silent truncation.
        """
        if not self._writable:
            raise ValueError("cannot write to a read-only reader")
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        if offset + len(data) > self._length:
            raise ValueError("write overruns the region")
        self._data[self._base + offset : self._base + offset + len(data)] = data

    def buffer(self) -> memoryview:
        """A buffer over this region for the underlying filesystem class.

        On a writable reader this is a *live* window onto the backing
        store, so mutations the filesystem makes reach the file. On a
        read-only reader it is a private copy, so a stray write cannot
        corrupt a shared (possibly read-only-mapped) backing.
        """
        if self._writable:
            return memoryview(self._data)[self._base : self._base + self._length]
        return memoryview(bytearray(self.read(0, self._length)))

    def find(self, needle: bytes, start: int = 0) -> int:
        """Region-relative offset of the first *needle* at/after *start*, or -1.

        Searches only within this region, in place (via ``mmap.find`` /
        ``bytes.find``) so a large image is not copied.
        """
        start = max(start, 0)
        if start >= self._length:
            return -1
        abs_start = self._base + start
        abs_end = self._base + self._length
        data = self._data
        if hasattr(data, "find"):
            index = data.find(needle, abs_start, abs_end)
        else:
            index = bytes(data).find(needle, abs_start, abs_end)
        return -1 if index < 0 else index - self._base

    def window(self, offset: int, length: int) -> "ImageReader":
        """A sub-region reader over ``[offset, offset + length)``.

        Shares this reader's backing buffer (no copy) and is clamped to
        what is available. It does **not** own the underlying file/mmap —
        the top-level reader does — so closing a window is a no-op.
        """
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        start = min(offset, self._length)
        end = min(offset + length, self._length)
        return ImageReader(
            self._data,
            base=self._base + start,
            length=end - start,
            writable=self._writable,
        )

    def close(self) -> None:
        for closeable in self._closeables:
            with suppress(Exception):
                closeable.close()
        self._closeables = ()

    def __enter__(self) -> "ImageReader":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def reader_for(
    source: ImageSource,
    *,
    suffix_hint: str | None = None,
    writable: bool = False,
) -> ImageReader:
    """Build an :class:`ImageReader` for *source*.

    Accepts an existing reader (returned unchanged), an in-memory buffer,
    or a filesystem path. Path sources are memory-mapped so a large
    hard-disc image is not read wholesale; the mapping is released when
    the reader is closed. *writable* maps the file for writing, so writes
    through the reader (and mutations of :meth:`ImageReader.buffer`) reach
    the file directly — used by the mutating CLI commands.
    """
    if isinstance(source, ImageReader):
        return source
    if isinstance(source, (bytes, bytearray, memoryview)):
        # A bytearray/memoryview is mutable in place; bytes is not. Only
        # claim writability when the buffer can actually take a write.
        can_write = writable and not isinstance(source, bytes)
        return ImageReader(source, suffix=suffix_hint, writable=can_write)
    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = suffix_hint if suffix_hint is not None else path.suffix
        if path.stat().st_size == 0:
            return ImageReader(b"", suffix=suffix, writable=writable)
        handle = path.open("r+b" if writable else "rb")
        access = mmap.ACCESS_WRITE if writable else mmap.ACCESS_READ
        mapping = mmap.mmap(handle.fileno(), 0, access=access)
        return ImageReader(
            mapping, suffix=suffix, writable=writable, _closeables=(mapping, handle)
        )
    raise TypeError(f"cannot build an ImageReader from {type(source).__name__}")
