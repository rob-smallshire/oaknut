"""Tests for the BBC BASIC data-file (PRINT#/INPUT#/BPUT#/BGET#) API."""

from __future__ import annotations

import io

import pytest
from oaknut.basic.datafile import (
    BbcBasicDataFile,
    BbcBasicDataReader,
    BbcBasicDataWriter,
)
from oaknut.basic.datafile import (
    open as open_datafile,
)
from oaknut.basic.exceptions import (
    DataFileTypeMismatchError,
    Float5RangeError,
    IntegerRangeError,
    StringTooLongError,
    TruncatedRecordError,
    UnknownTagError,
)


def _written(values, **kwargs) -> bytes:
    """Return the wire bytes produced by writing *values* via write()."""
    stream = io.BytesIO()
    with open_datafile(stream, "w", **kwargs) as f:
        for value in values:
            f.write(value)
    return stream.getvalue()


class TestWireFormat:
    """The byte-exact examples from data-files.md §3.2."""

    def test_integer(self) -> None:
        assert _written([0x12345678]) == bytes.fromhex("40 12345678".replace(" ", ""))

    def test_small_integer(self) -> None:
        assert _written([42]) == bytes.fromhex("400000002a")

    def test_string_is_length_prefixed_and_reversed(self) -> None:
        assert _written(["AB"]) == bytes.fromhex("00024241")

    def test_real_is_exponent_last(self) -> None:
        assert _written([1.0]) == bytes.fromhex("ff0000000081")

    def test_negative_real(self) -> None:
        assert _written([-1.0]) == bytes.fromhex("ff0000008081")

    def test_bytes_are_raw_and_untagged(self) -> None:
        assert _written([b"\x01\x02\x03"]) == b"\x01\x02\x03"

    def test_empty_string(self) -> None:
        assert _written([""]) == bytes.fromhex("0000")


class TestPolymorphicRoundTrip:
    def test_mixed_values_round_trip(self) -> None:
        values = [42, "HELLO", 3.5, -17, "", 0.0]
        data = _written(values)
        with open_datafile(io.BytesIO(data), "r") as f:
            assert list(f) == values

    def test_read_returns_none_at_eof(self) -> None:
        with open_datafile(io.BytesIO(_written([1])), "r") as f:
            assert f.read() == 1
            assert f.read() is None

    def test_read_types(self) -> None:
        with open_datafile(io.BytesIO(_written([7, "x", 1.5])), "r") as f:
            assert isinstance(f.read(), int)
            assert isinstance(f.read(), str)
            assert isinstance(f.read(), float)


class TestTypedReads:
    def test_typed_reads_match(self) -> None:
        with open_datafile(io.BytesIO(_written([5, "hi", 2.5])), "r") as f:
            assert f.read_int() == 5
            assert f.read_str() == "hi"
            assert f.read_float() == 2.5

    def test_typed_read_mismatch_raises_and_restores_position(self) -> None:
        with open_datafile(io.BytesIO(_written(["str"])), "r") as f:
            start = f.tell()
            with pytest.raises(DataFileTypeMismatchError):
                f.read_int()
            assert f.tell() == start  # position restored to the record boundary
            assert f.read_str() == "str"

    def test_typed_read_raises_eoferror_at_eof(self) -> None:
        with open_datafile(io.BytesIO(b""), "r") as f:
            with pytest.raises(EOFError):
                f.read_int()


class TestRawBytes:
    def test_read_byte_and_bytes(self) -> None:
        with open_datafile(io.BytesIO(b"\x01\x02\x03\x04"), "r") as f:
            assert f.read_byte() == 1
            assert f.read_bytes(2) == b"\x02\x03"
            assert f.read_bytes() == b"\x04"
            assert f.read_bytes() == b""

    def test_read_byte_raises_eoferror_at_eof(self) -> None:
        with open_datafile(io.BytesIO(b""), "r") as f:
            with pytest.raises(EOFError):
                f.read_byte()

    def test_write_byte(self) -> None:
        stream = io.BytesIO()
        with open_datafile(stream, "w") as f:
            f.write_byte(0xAB)
        assert stream.getvalue() == b"\xab"


class TestTypedWritesAreStrict:
    def test_write_int_rejects_float(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(TypeError):
            f.write_int(3.0)

    def test_write_float_rejects_int(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(TypeError):
            f.write_float(3)

    def test_write_rejects_bool(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(TypeError):
            f.write(True)

    def test_write_rejects_unsupported_type(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(TypeError):
            f.write([1, 2, 3])

    def test_integer_out_of_range(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(IntegerRangeError):
            f.write_int(2**31)

    def test_string_too_long(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(StringTooLongError):
            f.write_str("x" * 256)

    def test_float_overflow(self) -> None:
        with open_datafile(io.BytesIO(), "w") as f, pytest.raises(Float5RangeError):
            f.write_float(1e40)


class TestCorruptStreams:
    def test_unknown_tag(self) -> None:
        with open_datafile(io.BytesIO(b"\x7f"), "r") as f, pytest.raises(UnknownTagError):
            f.read()

    def test_truncated_integer(self) -> None:
        with open_datafile(io.BytesIO(b"\x40\x00\x00"), "r") as f:
            with pytest.raises(TruncatedRecordError):
                f.read()

    def test_truncated_string_payload(self) -> None:
        with open_datafile(io.BytesIO(b"\x00\x05AB"), "r") as f:
            with pytest.raises(TruncatedRecordError):
                f.read()


class TestEncodingAndNewlines:
    def test_acorn_pound_sign_round_trips(self) -> None:
        # 0x60 is the pound sign in the Acorn character set.
        data = _written(["£"])
        assert data == bytes.fromhex("000160")
        with open_datafile(io.BytesIO(data), "r") as f:
            assert f.read() == "£"

    def test_newline_translated_to_cr_by_default(self) -> None:
        data = _written(["a\nb"])
        assert data == b"\x00\x03b\ra"  # reversed: 'b', CR, 'a'

    def test_newline_round_trips_universally(self) -> None:
        with open_datafile(io.BytesIO(_written(["a\nb"])), "r") as f:
            assert f.read() == "a\nb"

    def test_no_translation_when_newline_empty(self) -> None:
        data = _written(["a\nb"], newline="")
        assert data == b"\x00\x03b\na"

    def test_encoding_override(self) -> None:
        data = _written(["AB"], encoding="ascii")
        assert data == bytes.fromhex("00024241")


class TestRandomAccess:
    def test_tell_seek_extent(self) -> None:
        data = _written([1, 2, 3])
        with open_datafile(io.BytesIO(data), "r") as f:
            assert f.extent == len(data)
            assert f.read_int() == 1
            pos = f.tell()
            assert f.read_int() == 2
            f.seek(pos)
            assert f.read_int() == 2

    def test_at_eof(self) -> None:
        with open_datafile(io.BytesIO(_written([1])), "r") as f:
            assert not f.at_eof()
            f.read_int()
            assert f.at_eof()


class TestOpenModesAndOwnership:
    def test_mode_selects_class(self) -> None:
        assert isinstance(open_datafile(io.BytesIO(), "r"), BbcBasicDataReader)
        assert isinstance(open_datafile(io.BytesIO(), "w"), BbcBasicDataWriter)
        assert isinstance(open_datafile(io.BytesIO(), "r+"), BbcBasicDataFile)

    def test_reader_has_no_write(self) -> None:
        assert not hasattr(open_datafile(io.BytesIO(), "r"), "write")

    def test_borrowed_stream_not_closed(self) -> None:
        stream = io.BytesIO()
        with open_datafile(stream, "w") as f:
            f.write(1)
        assert not stream.closed

    def test_path_round_trip(self, tmp_path) -> None:
        path = tmp_path / "data.dat"
        with open_datafile(path, "w") as f:
            f.write_int(99)
            f.write_str("done")
        with open_datafile(path, "r") as f:
            assert f.read_int() == 99
            assert f.read_str() == "done"

    def test_update_mode_reads_and_writes(self) -> None:
        data = _written([1, 2])
        stream = io.BytesIO(data)
        with open_datafile(stream, "r+") as f:
            assert f.read_int() == 1
            f.write_int(99)
        with open_datafile(io.BytesIO(stream.getvalue()), "r") as f:
            assert f.read_int() == 1
            assert f.read_int() == 99

    def test_append_mode(self) -> None:
        stream = io.BytesIO(_written([1]))
        with open_datafile(stream, "a") as f:
            f.write_int(2)
        with open_datafile(io.BytesIO(stream.getvalue()), "r") as f:
            assert list(f) == [1, 2]

    def test_operation_on_closed_file_raises(self) -> None:
        f = open_datafile(io.BytesIO(_written([1])), "r")
        f.close()
        with pytest.raises(ValueError):
            f.read()

    def test_invalid_mode(self) -> None:
        with pytest.raises(ValueError):
            open_datafile(io.BytesIO(), "rx")
