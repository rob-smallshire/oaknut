"""Bounded raw-byte access to a disc image, for probing.

Probers read small, fixed regions of an image — catalogue sectors,
magic numbers, free-space-map checksums — at absolute byte offsets,
before any geometry is known. :class:`ImageReader` gives them exactly
that and nothing more.

Reads past the end of the image are *clamped*: a short or empty result
is returned rather than raising. A prober can therefore inspect a
truncated or surprisingly-small image without special-casing its
length — a region that isn't there simply reads as fewer bytes.
"""

from __future__ import annotations

import mmap
from contextlib import suppress
from pathlib import Path
from typing import Union

ImageSource = Union["ImageReader", bytes, bytearray, memoryview, str, Path]


class ImageReader:
    """Clamped, read-only byte access to a disc image.

    Construct from any object supporting ``len()`` and slicing (bytes,
    a ``memoryview``, or an :class:`mmap.mmap`). Prefer
    :func:`reader_for`, which builds the right backing for a path or an
    in-memory buffer and manages the file handle.

    Usable as a context manager; exiting closes any file/mmap resources
    the reader owns.
    """

    def __init__(self, data, *, suffix: str | None = None, _closeables=()):
        self._data = data
        self._suffix = suffix.lower() if suffix else None
        self._closeables = tuple(_closeables)

    @property
    def size(self) -> int:
        """Total number of bytes in the image."""
        return len(self._data)

    @property
    def suffix(self) -> str | None:
        """The source file extension (lower-cased, with dot), if known.

        A *hint* for the coordinator's tie-breaking only — probers
        identify by content and should ignore it.
        """
        return self._suffix

    def read(self, offset: int, length: int) -> bytes:
        """Return up to *length* bytes starting at *offset*.

        The result is clamped to the image bounds: reading at or past
        the end yields ``b""``, and a range that overruns the end yields
        only the bytes that exist.
        """
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
        if length < 0:
            raise ValueError(f"length must be non-negative, got {length}")
        size = len(self._data)
        if offset >= size or length == 0:
            return b""
        end = min(offset + length, size)
        return bytes(self._data[offset:end])

    def find(self, needle: bytes, start: int = 0) -> int:
        """Return the offset of the first *needle* at or after *start*, or -1.

        Delegates to the backing object's own ``find`` (``mmap.find`` for
        path-backed images, ``bytes.find`` for buffers) so a large image
        is scanned in place rather than copied. A prober looking for a
        magic number that may sit deep in a hard-disc image should use
        this, then check alignment, rather than reading the whole image.
        """
        start = max(start, 0)
        data = self._data
        if hasattr(data, "find"):
            return data.find(needle, start)
        return bytes(data).find(needle, start)

    def close(self) -> None:
        for closeable in self._closeables:
            with suppress(Exception):
                closeable.close()
        self._closeables = ()

    def __enter__(self) -> "ImageReader":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def reader_for(source: ImageSource, *, suffix_hint: str | None = None) -> ImageReader:
    """Build an :class:`ImageReader` for *source*.

    Accepts an existing :class:`ImageReader` (returned unchanged), an
    in-memory buffer (``bytes``/``bytearray``/``memoryview``), or a
    filesystem path (``str``/``Path``). Path sources are memory-mapped
    read-only so large hard-disc images are not pulled wholesale into
    memory; the mapping is released when the reader is closed.

    *suffix_hint* overrides the extension carried for tie-breaking;
    otherwise a path's own suffix is used.
    """
    if isinstance(source, ImageReader):
        return source
    if isinstance(source, (bytes, bytearray, memoryview)):
        return ImageReader(source, suffix=suffix_hint)
    if isinstance(source, (str, Path)):
        path = Path(source)
        suffix = suffix_hint if suffix_hint is not None else path.suffix
        handle = path.open("rb")
        if path.stat().st_size == 0:
            # mmap cannot map an empty file.
            handle.close()
            return ImageReader(b"", suffix=suffix)
        mapping = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        return ImageReader(mapping, suffix=suffix, _closeables=(mapping, handle))
    raise TypeError(f"cannot build an ImageReader from {type(source).__name__}")
