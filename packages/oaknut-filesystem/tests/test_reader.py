"""Tests for the windowable ImageReader."""

import pytest
from oaknut.filesystem import ImageReader, reader_for


class TestReadAndFind:
    def test_size_and_read(self):
        reader = ImageReader(b"abcdef")
        assert reader.size == 6
        assert reader.read(2, 3) == b"cde"

    def test_read_past_end_is_clamped(self):
        assert ImageReader(b"abc").read(1, 100) == b"bc"
        assert ImageReader(b"abc").read(3, 10) == b""

    def test_read_rejects_negatives(self):
        with pytest.raises(ValueError):
            ImageReader(b"abc").read(-1, 1)
        with pytest.raises(ValueError):
            ImageReader(b"abc").read(0, -1)

    def test_find(self):
        reader = ImageReader(b"....AFS0....AFS0")
        assert reader.find(b"AFS0") == 4
        assert reader.find(b"AFS0", 5) == 12
        assert reader.find(b"nope") == -1


class TestWindow:
    def test_window_is_a_clamped_subview(self):
        reader = ImageReader(b"0123456789")
        window = reader.window(3, 4)
        assert window.size == 4
        assert window.read(0, 4) == b"3456"
        # Reads are region-relative and clamped to the window.
        assert window.read(2, 100) == b"56"

    def test_window_find_is_region_relative(self):
        reader = ImageReader(b"xxxxAFS0xx")
        window = reader.window(4, 4)
        assert window.find(b"AFS0") == 0
        # A needle outside the window is not found.
        assert ImageReader(b"AFS0xxxxxx").window(4, 4).find(b"AFS0") == -1

    def test_window_of_window(self):
        reader = ImageReader(b"0123456789")
        assert reader.window(2, 6).window(1, 2).read(0, 2) == b"34"

    def test_window_past_end_clamps_to_empty(self):
        assert ImageReader(b"abc").window(10, 4).size == 0


class TestReaderFor:
    def test_buffer_source(self):
        with reader_for(b"hello") as reader:
            assert reader.size == 5
            assert reader.suffix is None

    def test_existing_reader_passes_through(self):
        original = ImageReader(b"x")
        assert reader_for(original) is original

    def test_path_source_is_mapped(self, tmp_path):
        image_filepath = tmp_path / "disc.ssd"
        image_filepath.write_bytes(b"\x01\x02\x03\x04")
        with reader_for(image_filepath) as reader:
            assert reader.size == 4
            assert reader.suffix == ".ssd"
            assert reader.read(0, 2) == b"\x01\x02"

    def test_empty_path_source(self, tmp_path):
        image_filepath = tmp_path / "empty.dat"
        image_filepath.write_bytes(b"")
        with reader_for(image_filepath) as reader:
            assert reader.size == 0

    def test_unsupported_source_rejected(self):
        with pytest.raises(TypeError):
            reader_for(1234)


class TestWritable:
    def test_default_reader_is_not_writable(self):
        with reader_for(b"hello") as reader:
            assert reader.writable is False

    def test_write_through_file_persists(self, tmp_path):
        image_filepath = tmp_path / "disc.ssd"
        image_filepath.write_bytes(bytes(16))
        with reader_for(image_filepath, writable=True) as reader:
            assert reader.writable is True
            reader.write(4, b"\xde\xad\xbe\xef")
        # Reopened from disk, the bytes are there — the write hit the file.
        assert image_filepath.read_bytes()[4:8] == b"\xde\xad\xbe\xef"

    def test_buffer_is_a_live_window_when_writable(self, tmp_path):
        # The adapter builds its filesystem class over buffer(); mutating
        # that buffer must reach the file.
        image_filepath = tmp_path / "disc.ssd"
        image_filepath.write_bytes(bytes(8))
        with reader_for(image_filepath, writable=True) as reader:
            buffer = reader.buffer()
            buffer[0:2] = b"\x01\x02"
        assert image_filepath.read_bytes()[0:2] == b"\x01\x02"

    def test_buffer_is_a_private_copy_when_read_only(self):
        # A read-only reader hands out a copy, so a stray write cannot
        # corrupt a shared (possibly ACCESS_READ) backing.
        reader = ImageReader(b"abcd")
        buffer = reader.buffer()
        buffer[0:1] = b"Z"
        assert reader.read(0, 4) == b"abcd"

    def test_write_on_read_only_reader_raises(self):
        reader = ImageReader(b"abcd")
        with pytest.raises(ValueError, match="read-only"):
            reader.write(0, b"Z")

    def test_window_inherits_writability(self, tmp_path):
        image_filepath = tmp_path / "disc.ssd"
        image_filepath.write_bytes(bytes(16))
        with reader_for(image_filepath, writable=True) as reader:
            window = reader.window(8, 4)
            assert window.writable is True
            window.write(0, b"\xaa\xbb")
        assert image_filepath.read_bytes()[8:10] == b"\xaa\xbb"
