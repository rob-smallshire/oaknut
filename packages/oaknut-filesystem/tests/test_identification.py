"""Tests for the identification result types."""

from oaknut.filesystem import Confidence, Identification, Partition


class TestConfidence:
    def test_ordering(self):
        assert (
            Confidence.CERTAIN
            > Confidence.STRONG
            > Confidence.PROBABLE
            > Confidence.POSSIBLE
        )


class TestPartition:
    def test_selector_omits_zero_index(self):
        assert Partition("afs", 0, 100).selector == "afs"

    def test_selector_includes_nonzero_index(self):
        assert Partition("afs", 0, 100, index=1).selector == "afs.1"


class TestIdentification:
    def test_identified_flag(self):
        assert Identification("adfs", Confidence.STRONG).identified is True
        assert Identification("", Confidence.POSSIBLE).identified is False

    def test_with_contained_is_a_copy(self):
        root = Identification("adfs", Confidence.STRONG)
        child = Identification("afs", Confidence.CERTAIN)
        populated = root.with_contained((child,))
        assert populated.contained == (child,)
        assert root.contained == ()  # original unchanged (frozen)
        assert populated.filesystem == "adfs"
