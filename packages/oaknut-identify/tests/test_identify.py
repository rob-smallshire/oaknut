"""Tests for the identification primitives: reader, confidence, ranking.

End-to-end cascade behaviour against real reference images lives with
the concrete probers (see oaknut-dfs). Here the cascade is exercised
with synthetic candidates so the ranking rules are pinned down
independently of which probers happen to be installed.
"""

import pytest
from oaknut.identify import Confidence, Identification, ImageReader, identify, reader_for
from oaknut.identify.coordinator import _rank
from oaknut.identify.prober import Prober


class TestConfidenceOrdering:
    def test_higher_means_more_certain(self):
        assert (
            Confidence.CERTAIN
            > Confidence.STRONG
            > Confidence.PROBABLE
            > Confidence.POSSIBLE
        )


class TestImageReader:
    def test_size_reports_buffer_length(self):
        assert ImageReader(b"abcdef").size == 6

    def test_read_returns_requested_slice(self):
        assert ImageReader(b"abcdef").read(2, 3) == b"cde"

    def test_read_past_end_is_clamped(self):
        # A region that overruns the end yields only what exists.
        assert ImageReader(b"abc").read(1, 100) == b"bc"

    def test_read_at_or_beyond_end_is_empty(self):
        assert ImageReader(b"abc").read(3, 10) == b""
        assert ImageReader(b"abc").read(99, 10) == b""

    def test_zero_length_read_is_empty(self):
        assert ImageReader(b"abc").read(0, 0) == b""

    def test_negative_offset_or_length_rejected(self):
        with pytest.raises(ValueError):
            ImageReader(b"abc").read(-1, 1)
        with pytest.raises(ValueError):
            ImageReader(b"abc").read(0, -1)

    def test_suffix_is_lowercased(self):
        assert ImageReader(b"", suffix=".SSD").suffix == ".ssd"


class TestReaderFor:
    def test_buffer_source(self):
        with reader_for(b"hello") as reader:
            assert reader.size == 5
            assert reader.suffix is None

    def test_existing_reader_passes_through(self):
        original = ImageReader(b"x")
        assert reader_for(original) is original

    def test_path_source_is_memory_mapped(self, tmp_path):
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
            assert reader.read(0, 10) == b""

    def test_suffix_hint_overrides_path_suffix(self, tmp_path):
        image_filepath = tmp_path / "mystery.img"
        image_filepath.write_bytes(b"abcd")
        with reader_for(image_filepath, suffix_hint=".ssd") as reader:
            assert reader.suffix == ".ssd"

    def test_unsupported_source_type_rejected(self):
        with pytest.raises(TypeError):
            reader_for(1234)


class _FakeProber(Prober):
    """A stand-in prober for ranking tests."""

    def __init__(self, name, family, extensions=frozenset(), priority=0):
        super().__init__(name=name)
        self.family = family
        self.extensions = extensions
        self.priority = priority

    def probe(self, reader):  # pragma: no cover - not exercised here
        return ()


def _ident(prober_name, family, confidence):
    return Identification(prober_name=prober_name, family=family, confidence=confidence)


class TestRanking:
    def test_confidence_dominates(self):
        probers = {
            "weak": _FakeProber("weak", "dfs"),
            "strong": _FakeProber("strong", "adfs"),
        }
        candidates = [
            _ident("weak", "dfs", Confidence.POSSIBLE),
            _ident("strong", "adfs", Confidence.CERTAIN),
        ]
        ranked = _rank(candidates, probers, suffix=None)
        assert [c.prober_name for c in ranked] == ["strong", "weak"]

    def test_extension_breaks_ties(self):
        probers = {
            "dfs": _FakeProber("dfs", "dfs", extensions=frozenset({".ssd"})),
            "adfs": _FakeProber("adfs", "adfs", extensions=frozenset({".adf"})),
        }
        # Equal confidence; the .ssd extension should favour the dfs prober.
        candidates = [
            _ident("adfs", "adfs", Confidence.PROBABLE),
            _ident("dfs", "dfs", Confidence.PROBABLE),
        ]
        ranked = _rank(candidates, probers, suffix=".ssd")
        assert ranked[0].prober_name == "dfs"

    def test_priority_breaks_remaining_ties(self):
        probers = {
            "lo": _FakeProber("lo", "dfs", priority=0),
            "hi": _FakeProber("hi", "dfs", priority=10),
        }
        candidates = [
            _ident("lo", "dfs", Confidence.PROBABLE),
            _ident("hi", "dfs", Confidence.PROBABLE),
        ]
        ranked = _rank(candidates, probers, suffix=None)
        assert ranked[0].prober_name == "hi"

    def test_name_ascending_is_final_tiebreak(self):
        probers = {
            "bbb": _FakeProber("bbb", "dfs"),
            "aaa": _FakeProber("aaa", "dfs"),
        }
        candidates = [
            _ident("bbb", "dfs", Confidence.PROBABLE),
            _ident("aaa", "dfs", Confidence.PROBABLE),
        ]
        ranked = _rank(candidates, probers, suffix=None)
        assert [c.prober_name for c in ranked] == ["aaa", "bbb"]


class TestIdentifySmoke:
    def test_identify_returns_a_list(self):
        # Whatever probers are installed, identify() must return a list
        # and not raise on arbitrary bytes.
        result = identify(b"\x00" * 4096, suffix_hint=".unknown")
        assert isinstance(result, list)
