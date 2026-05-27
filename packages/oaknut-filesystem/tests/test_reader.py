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
