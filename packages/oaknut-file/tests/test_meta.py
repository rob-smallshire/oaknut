"""Tests for AcornMeta dataclass."""

import pytest
from oaknut.file.meta import AcornMeta


class TestAcornMeta:
    def test_default_construction(self):
        meta = AcornMeta()
        assert meta.load_address is None
        assert meta.exec_address is None
        assert meta.access is None
        assert meta.filetype is None

    def test_construction_with_values(self):
        meta = AcornMeta(load_address=0x1900, exec_address=0x8023, access=0x03)
        assert meta.load_address == 0x1900
        assert meta.exec_address == 0x8023
        assert meta.access == 0x03

    def test_has_metadata_true(self):
        meta = AcornMeta(load_address=0x1900)
        assert meta.has_metadata is True

    def test_has_metadata_false(self):
        meta = AcornMeta()
        assert meta.has_metadata is False


class TestFiletypeStamping:
    def test_filetype_stamped(self):
        meta = AcornMeta(load_address=0xFFFF0E10)
        assert meta.is_filetype_stamped is True

    def test_not_filetype_stamped(self):
        meta = AcornMeta(load_address=0x1900)
        assert meta.is_filetype_stamped is False

    def test_none_not_filetype_stamped(self):
        meta = AcornMeta()
        assert meta.is_filetype_stamped is False

    def test_marker_is_structural_even_when_load_equals_exec(self):
        # The archival filetype marker is the pure top-12-bits test; the
        # load == exec (FileSwitch datestamp) rule is applied by the live
        # filesystem display, not by this structural predicate.
        meta = AcornMeta(load_address=0xFFFFFA00, exec_address=0xFFFFFA00)
        assert meta.is_filetype_stamped is True
        assert meta.infer_filetype() == 0xFFA

    def test_infer_filetype_from_load(self):
        meta = AcornMeta(load_address=0xFFFF0E10)
        assert meta.infer_filetype() == 0xF0E

    def test_infer_filetype_basic(self):
        meta = AcornMeta(load_address=0xFFFFFB00)
        assert meta.infer_filetype() == 0xFFB

    def test_infer_filetype_text(self):
        meta = AcornMeta(load_address=0xFFFFFF52)
        assert meta.infer_filetype() == 0xFFF

    def test_infer_filetype_falls_back_to_field(self):
        meta = AcornMeta(load_address=0x1900, filetype=0xFFB)
        assert meta.infer_filetype() == 0xFFB

    def test_infer_filetype_none(self):
        meta = AcornMeta(load_address=0x1900)
        assert meta.infer_filetype() is None
