"""Reading and writing BBC BASIC data files.

BBC BASIC data files are the channel-based files created with ``OPENOUT``
/ ``OPENIN`` / ``OPENUP`` and written and read with ``PRINT#`` /
``INPUT#`` (type-tagged records) and ``BPUT#`` / ``BGET#`` (raw bytes).
The tagged format is private to BASIC and idiosyncratic:

- An **integer** is a ``&40`` tag then four bytes, most-significant first.
- A **real** is a ``&FF`` tag then five packed floating-point bytes,
  *exponent last* — the natural :mod:`oaknut.basic.float5` order reversed.
- A **string** is a ``&00`` tag, a one-byte length, then the characters
  **reversed**.

This module presents that format as a Python file object. The
context-managed classes follow a diamond hierarchy
(:class:`BbcBasicDataFileBase` → :class:`BbcBasicDataReader` /
:class:`BbcBasicDataWriter` → :class:`BbcBasicDataFile`), and the
module-level :func:`open` constructs the right one from a ``mode`` string
in the style of the built-in ``open``::

    from oaknut.basic import datafile

    with datafile.open("scores.dat", "w") as f:
        f.write("ALICE")     # polymorphic: str -> string record
        f.write(42)          # int -> integer record
        f.write(3.5)         # float -> real record

    with datafile.open("scores.dat", "r") as f:
        for value in f:      # yields "ALICE", 42, 3.5
            ...

The polymorphic :meth:`~BbcBasicDataWriter.write` chooses the record type
from the Python type; the typed ``write_int`` / ``write_float`` /
``write_str`` perform no coercion and raise on the wrong type. Strings
are encoded with the ``acorn`` codec by default, with built-in-``open``
style newline translation.
"""

from __future__ import annotations

import builtins
import os
import struct
from typing import IO, Union

import oaknut.codecs  # noqa: F401 - registers the "acorn" codec as a side effect
from oaknut.basic.exceptions import (
    DataFileTypeMismatchError,
    IntegerRangeError,
    StringTooLongError,
    TruncatedRecordError,
    UnknownTagError,
)
from oaknut.basic.float5 import pack_float5, unpack_float5

__all__ = [
    "BbcBasicDataFile",
    "BbcBasicDataFileBase",
    "BbcBasicDataReader",
    "BbcBasicDataWriter",
    "open",
]

# Type tags: BASIC's own internal type code, written ahead of each value.
TAG_STRING = 0x00
TAG_INTEGER = 0x40
TAG_REAL = 0xFF

_INT_MIN = -(2**31)
_INT_MAX = 2**31 - 1
_MAX_STRING_LENGTH = 0xFF

_LEGAL_NEWLINES = (None, "", "\r", "\n", "\r\n")

FileSource = Union[str, os.PathLike, IO[bytes]]


class BbcBasicDataFileBase:
    """Common state and positioning for a BBC BASIC data file.

    Holds the underlying binary stream, the string encoding and newline
    policy, and ownership of the stream (a path opened by :func:`open` is
    owned and closed on exit; a caller-supplied stream is borrowed and
    left open). Subclasses add the read and/or write vocabulary.
    """

    def __init__(
        self,
        stream: IO[bytes],
        *,
        owns_stream: bool,
        encoding: str,
        newline: str | None,
        errors: str,
    ) -> None:
        self._stream = stream
        self._owns_stream = owns_stream
        self._encoding = encoding
        self._newline = newline
        self._errors = errors
        self._closed = False

    # -- lifecycle ----------------------------------------------------------

    def _check_open(self) -> None:
        if self._closed:
            raise ValueError("I/O operation on closed BBC BASIC data file")

    def close(self) -> None:
        """Close the file, closing the stream only if this object owns it."""
        if not self._closed:
            try:
                if self._owns_stream:
                    self._stream.close()
            finally:
                self._closed = True

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> "BbcBasicDataFileBase":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.close()
        return False

    # -- position and extent (PTR# / EXT# / EOF#) ---------------------------

    def tell(self) -> int:
        """Return the current byte position (``PTR#``)."""
        self._check_open()
        return self._stream.tell()

    def seek(self, position: int, whence: int = os.SEEK_SET) -> int:
        """Set the current byte position (``PTR#=``); return the new position."""
        self._check_open()
        return self._stream.seek(position, whence)

    @property
    def extent(self) -> int:
        """The length of the file in bytes (``EXT#``)."""
        self._check_open()
        current = self._stream.tell()
        end = self._stream.seek(0, os.SEEK_END)
        self._stream.seek(current)
        return end

    def at_eof(self) -> bool:
        """Return whether the position is at or past the end (``EOF#``)."""
        self._check_open()
        return self._stream.tell() >= self.extent

    # -- newline translation ------------------------------------------------

    def _encode_newlines(self, text: str) -> str:
        if self._newline is None:
            return text.replace("\n", "\r")
        if self._newline == "":
            return text
        return text.replace("\n", self._newline)

    def _decode_newlines(self, text: str) -> str:
        if self._newline is None:
            return text.replace("\r\n", "\n").replace("\r", "\n")
        if self._newline in ("", "\n"):
            return text
        return text.replace(self._newline, "\n")


class BbcBasicDataReader(BbcBasicDataFileBase):
    """A BBC BASIC data file open for reading (``OPENIN``)."""

    # -- tagged records (INPUT#) -------------------------------------------

    def read(self) -> int | float | str | None:
        """Read the next tagged record, adapting to its type.

        Returns the value as an ``int``, ``float`` or ``str`` according to
        the record's type tag, or ``None`` at end of file (so a read loop
        can be written ``while (v := f.read()) is not None``).

        Raises:
            UnknownTagError: The next byte is not a known type tag.
            TruncatedRecordError: A record ran past the end of the file.
        """
        self._check_open()
        offset = self._stream.tell()
        tag_byte = self._stream.read(1)
        if not tag_byte:
            return None
        return self._read_payload(tag_byte[0], offset)

    def read_int(self) -> int:
        """Read the next record, which must be an integer.

        Raises:
            EOFError: At end of file.
            DataFileTypeMismatchError: The next record is not an integer
                (the position is restored to the start of the record).
            TruncatedRecordError: The record ran past the end of the file.
        """
        return self._read_typed(TAG_INTEGER, "integer")

    def read_float(self) -> float:
        """Read the next record, which must be a real. See :meth:`read_int`."""
        return self._read_typed(TAG_REAL, "real")

    def read_str(self) -> str:
        """Read the next record, which must be a string. See :meth:`read_int`."""
        return self._read_typed(TAG_STRING, "string")

    def _read_typed(self, expected_tag: int, type_name: str) -> int | float | str:
        self._check_open()
        offset = self._stream.tell()
        tag_byte = self._stream.read(1)
        if not tag_byte:
            raise EOFError("no more records in BBC BASIC data file")
        tag = tag_byte[0]
        if tag != expected_tag:
            self._stream.seek(offset)
            raise DataFileTypeMismatchError(type_name, tag, offset)
        return self._read_payload(tag, offset)

    def _read_payload(self, tag: int, offset: int) -> int | float | str:
        if tag == TAG_INTEGER:
            return self._read_integer(offset)
        if tag == TAG_REAL:
            return self._read_real(offset)
        if tag == TAG_STRING:
            return self._read_string(offset)
        self._stream.seek(offset)
        raise UnknownTagError(tag, offset)

    def _read_integer(self, offset: int) -> int:
        payload = self._stream.read(4)
        if len(payload) < 4:
            raise TruncatedRecordError(offset, "an integer needs 4 bytes")
        return struct.unpack(">i", payload)[0]

    def _read_real(self, offset: int) -> float:
        payload = self._stream.read(5)
        if len(payload) < 5:
            raise TruncatedRecordError(offset, "a real needs 5 bytes")
        # On the wire the packed real is exponent-last, so reverse it back
        # to the natural exponent-first order float5 expects.
        return unpack_float5(payload[::-1])

    def _read_string(self, offset: int) -> str:
        length_byte = self._stream.read(1)
        if not length_byte:
            raise TruncatedRecordError(offset, "a string needs a length byte")
        length = length_byte[0]
        payload = self._stream.read(length)
        if len(payload) < length:
            raise TruncatedRecordError(offset, f"a string of {length} bytes was truncated")
        decoded = payload[::-1].decode(self._encoding, self._errors)
        return self._decode_newlines(decoded)

    # -- raw bytes (BGET#) --------------------------------------------------

    def read_byte(self) -> int:
        """Read one raw byte (``BGET#``).

        Raises:
            EOFError: At end of file.
        """
        self._check_open()
        byte = self._stream.read(1)
        if not byte:
            raise EOFError("no more bytes in BBC BASIC data file")
        return byte[0]

    def read_bytes(self, size: int = -1) -> bytes:
        """Read up to *size* raw bytes (``BGET#``), or all remaining if ``-1``.

        Follows binary-stream semantics: returns fewer bytes than asked
        at end of file, and ``b""`` once exhausted (no exception).
        """
        self._check_open()
        if size is None or size < 0:
            return self._stream.read()
        return self._stream.read(size)

    # -- iteration over tagged records --------------------------------------

    def __iter__(self) -> "BbcBasicDataReader":
        return self

    def __next__(self) -> int | float | str:
        value = self.read()
        if value is None:
            raise StopIteration
        return value


class BbcBasicDataWriter(BbcBasicDataFileBase):
    """A BBC BASIC data file open for writing (``OPENOUT`` / append)."""

    # -- tagged records (PRINT#) -------------------------------------------

    def write(self, value: int | float | str | bytes | bytearray) -> None:
        """Write *value*, choosing the record type from its Python type.

        ``int`` → integer record, ``float`` → real record, ``str`` →
        string record, ``bytes``/``bytearray`` → raw bytes (untagged, as
        ``BPUT#`` would). ``bool`` and any other type raise ``TypeError``;
        BBC BASIC has no boolean type.
        """
        if isinstance(value, bool):
            raise TypeError("BBC BASIC has no boolean type; use write_int explicitly")
        if isinstance(value, int):
            self.write_int(value)
        elif isinstance(value, float):
            self.write_float(value)
        elif isinstance(value, str):
            self.write_str(value)
        elif isinstance(value, (bytes, bytearray)):
            self.write_bytes(value)
        else:
            raise TypeError(
                f"cannot write a {type(value).__name__} to a BBC BASIC data file "
                f"(expected int, float, str or bytes)"
            )

    def write_int(self, value: int) -> None:
        """Write an integer record. Raises ``TypeError`` for a non-int.

        Raises:
            IntegerRangeError: The value is outside the signed 32-bit range.
        """
        self._check_open()
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"write_int requires an int, got {type(value).__name__}")
        if not (_INT_MIN <= value <= _INT_MAX):
            raise IntegerRangeError(value)
        self._stream.write(bytes((TAG_INTEGER,)) + struct.pack(">i", value))

    def write_float(self, value: float) -> None:
        """Write a real record. Raises ``TypeError`` for a non-float.

        Raises:
            Float5RangeError: The value is too large for the 5-byte format.
        """
        self._check_open()
        if not isinstance(value, float):
            raise TypeError(f"write_float requires a float, got {type(value).__name__}")
        # float5 packs exponent-first; PRINT# stores the real reversed.
        self._stream.write(bytes((TAG_REAL,)) + pack_float5(value)[::-1])

    def write_str(self, value: str) -> None:
        """Write a string record. Raises ``TypeError`` for a non-str.

        Raises:
            StringTooLongError: The encoded string exceeds 255 bytes.
        """
        self._check_open()
        if not isinstance(value, str):
            raise TypeError(f"write_str requires a str, got {type(value).__name__}")
        encoded = self._encode_newlines(value).encode(self._encoding, self._errors)
        if len(encoded) > _MAX_STRING_LENGTH:
            raise StringTooLongError(len(encoded))
        self._stream.write(bytes((TAG_STRING, len(encoded))) + encoded[::-1])

    # -- raw bytes (BPUT#) --------------------------------------------------

    def write_bytes(self, value: bytes | bytearray) -> None:
        """Write raw bytes with no tag or framing (``BPUT#``)."""
        self._check_open()
        if not isinstance(value, (bytes, bytearray)):
            raise TypeError(f"write_bytes requires bytes, got {type(value).__name__}")
        self._stream.write(value)

    def write_byte(self, value: int) -> None:
        """Write one raw byte (``BPUT#``).

        Raises:
            TypeError: *value* is not an int.
            ValueError: *value* is not in the range 0-255.
        """
        self._check_open()
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"write_byte requires an int, got {type(value).__name__}")
        if not 0 <= value <= 0xFF:
            raise ValueError(f"byte value {value} is out of range (0-255)")
        self._stream.write(bytes((value,)))


class BbcBasicDataFile(BbcBasicDataReader, BbcBasicDataWriter):
    """A BBC BASIC data file open for both reading and writing (``OPENUP``)."""


# Mode -> (binary file mode, class, position action for a borrowed stream).
_MODE_TABLE = {
    "r": ("rb", BbcBasicDataReader, "start"),
    "w": ("wb", BbcBasicDataWriter, "truncate"),
    "a": ("ab", BbcBasicDataWriter, "end"),
    "r+": ("r+b", BbcBasicDataFile, "start"),
    "w+": ("w+b", BbcBasicDataFile, "truncate"),
    "a+": ("a+b", BbcBasicDataFile, "end"),
}


def _apply_position(stream: IO[bytes], action: str) -> None:
    """Position a borrowed stream to match the requested open mode."""
    if not stream.seekable():
        return
    if action == "start":
        stream.seek(0)
    elif action == "truncate":
        stream.seek(0)
        stream.truncate()
    elif action == "end":
        stream.seek(0, os.SEEK_END)


def open(
    file: FileSource,
    mode: str = "r",
    *,
    encoding: str = "acorn",
    newline: str | None = None,
    errors: str = "strict",
) -> BbcBasicDataFileBase:
    """Open a BBC BASIC data file, styled on the built-in ``open``.

    Args:
        file: A filesystem path, or an already-open binary stream (e.g.
            ``io.BytesIO``). A path is opened and owned (closed on exit); a
            stream is borrowed and left open, but is repositioned to suit
            *mode* (rewound for read/update, truncated for ``w``, moved to
            the end for append).
        mode: One of ``r`` (read), ``w`` (create/truncate for write),
            ``a`` (append), or the ``+`` update variants ``r+`` / ``w+`` /
            ``a+`` (read and write). Binary is implicit.
        encoding: Codec for string records; the BBC ``acorn`` set by default.
        newline: Newline translation, as for the built-in ``open``. The
            default (``None``) translates ``\\n`` to the Acorn ``\\r`` on
            write and any of ``\\r\\n`` / ``\\r`` / ``\\n`` to ``\\n`` on
            read. ``""`` disables translation.
        errors: Codec error policy for string records.

    Returns:
        A :class:`BbcBasicDataReader`, :class:`BbcBasicDataWriter` or
        :class:`BbcBasicDataFile` according to *mode*.

    Raises:
        ValueError: *mode* or *newline* is not recognised.
    """
    if mode not in _MODE_TABLE:
        raise ValueError(f"invalid mode: {mode!r} (use one of {', '.join(_MODE_TABLE)})")
    if newline not in _LEGAL_NEWLINES:
        raise ValueError(f"illegal newline value: {newline!r}")

    file_mode, cls, position = _MODE_TABLE[mode]

    if isinstance(file, (str, os.PathLike)):
        stream = builtins.open(file, file_mode)
        owns_stream = True
    else:
        stream = file
        owns_stream = False
        _apply_position(stream, position)

    return cls(
        stream,
        owns_stream=owns_stream,
        encoding=encoding,
        newline=newline,
        errors=errors,
    )
