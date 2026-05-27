"""Tests for the identification cascade, driven by fake filesystems.

Real entry-point discovery is exercised once concrete filesystems are
registered (Phase B). Here the coordinator is fed an explicit filesystem
set, so ranking, recursion, and graceful no-match are pinned down
independently of what is installed — which is also how the
extensibility invariant (a partial install) is tested.
"""

import pytest
from oaknut.filesystem import (
    Confidence,
    Filesystem,
    GeometryGrammar,
    Identification,
    Partition,
    create_filesystem,
    filesystem_names,
    identify,
)
from oaknut.filesystem.exceptions import FilesystemExtensionError


class _FakeFilesystem(Filesystem):
    """Matches when its magic appears at offset 0 of the region."""

    def __init__(
        self,
        name,
        *,
        magic,
        confidence=Confidence.PROBABLE,
        reserved=(),
        extensions=frozenset(),
        priority=0,
    ):
        super().__init__(name=name)
        self._magic = magic
        self._confidence = confidence
        self._reserved = tuple(reserved)
        self.extensions = extensions
        self.priority = priority

    def probe(self, reader):
        if reader.read(0, len(self._magic)) == self._magic:
            return Identification(
                filesystem=self.name,
                confidence=self._confidence,
                evidence=(f"magic {self._magic!r}",),
                reserved_regions=self._reserved,
            )
        return None

    def open(self, reader, geometry):  # pragma: no cover - not exercised here
        raise NotImplementedError

    def geometry_grammar(self):
        return GeometryGrammar()


def _fss(*filesystems):
    return {fs.name: fs for fs in filesystems}


class TestSingleRegion:
    def test_match_yields_one_candidate(self):
        fss = _fss(_FakeFilesystem("acorn-dfs", magic=b"DFS!"))
        results = identify(b"DFS!" + b"\x00" * 100, filesystems=fss)
        assert len(results) == 1
        assert results[0].filesystem == "acorn-dfs"
        # The whole image is the candidate's partition.
        assert results[0].partition == Partition("acorn-dfs", 0, 104)

    def test_no_match_is_empty(self):
        fss = _fss(_FakeFilesystem("acorn-dfs", magic=b"DFS!"))
        assert identify(b"\x00" * 100, filesystems=fss) == []


class TestRanking:
    def test_confidence_dominates(self):
        fss = _fss(
            _FakeFilesystem("weak", magic=b"WK", confidence=Confidence.POSSIBLE),
            _FakeFilesystem("strong", magic=b"WK", confidence=Confidence.CERTAIN),
        )
        ranked = identify(b"WK" + b"\x00" * 10, filesystems=fss)
        assert [r.filesystem for r in ranked] == ["strong", "weak"]

    def test_extension_breaks_ties(self):
        fss = _fss(
            _FakeFilesystem("a", magic=b"XX", extensions=frozenset({".aaa"})),
            _FakeFilesystem("b", magic=b"XX", extensions=frozenset({".bbb"})),
        )
        ranked = identify(b"XX" + b"\x00" * 10, suffix_hint=".bbb", filesystems=fss)
        assert ranked[0].filesystem == "b"

    def test_priority_breaks_remaining_ties(self):
        fss = _fss(
            _FakeFilesystem("lo", magic=b"XX", priority=0),
            _FakeFilesystem("hi", magic=b"XX", priority=10),
        )
        ranked = identify(b"XX" + b"\x00" * 10, filesystems=fss)
        assert ranked[0].filesystem == "hi"


class TestRecursion:
    def test_reserved_region_is_identified_and_named(self):
        # Host matches at 0 and reserves bytes [512, 512+256); the tail
        # filesystem's magic sits there.
        image = bytearray(1024)
        image[0:4] = b"HOST"
        image[512:516] = b"TAIL"
        host = _FakeFilesystem(
            "adfs",
            magic=b"HOST",
            confidence=Confidence.STRONG,
            reserved=(Partition("", 512, 256),),
        )
        tail = _FakeFilesystem("afs", magic=b"TAIL", confidence=Confidence.CERTAIN)
        results = identify(bytes(image), filesystems=_fss(host, tail))
        assert results[0].filesystem == "adfs"
        (contained,) = results[0].contained
        assert contained.filesystem == "afs"
        # The contained partition is named by what was found, with the
        # host-relative offset preserved.
        assert contained.partition == Partition("afs", 512, 256, 0)

    def test_unidentified_reserved_region_is_reported(self):
        image = bytearray(1024)
        image[0:4] = b"HOST"
        # Nothing recognisable at the reserved region.
        host = _FakeFilesystem(
            "adfs", magic=b"HOST", reserved=(Partition("", 512, 256),)
        )
        results = identify(bytes(image), filesystems=_fss(host))
        (contained,) = results[0].contained
        assert contained.identified is False
        assert contained.partition.offset == 512

    def test_two_tail_partitions_of_one_kind_are_indexed(self):
        image = bytearray(2048)
        image[0:4] = b"HOST"
        image[512:516] = b"TAIL"
        image[1024:1028] = b"TAIL"
        host = _FakeFilesystem(
            "adfs",
            magic=b"HOST",
            reserved=(Partition("", 512, 256), Partition("", 1024, 256)),
        )
        tail = _FakeFilesystem("afs", magic=b"TAIL")
        results = identify(bytes(image), filesystems=_fss(host, tail))
        selectors = [c.partition.selector for c in results[0].contained]
        assert selectors == ["afs", "afs.1"]


class TestPartialInstall:
    def test_only_installed_filesystems_are_used(self):
        # The extensibility invariant in miniature: with only the DFS-like
        # filesystem "installed", an ADFS-like image is not recognised.
        only_dfs = _fss(_FakeFilesystem("acorn-dfs", magic=b"DFS!"))
        assert identify(b"ADFS" + b"\x00" * 100, filesystems=only_dfs) == []
        assert identify(b"DFS!" + b"\x00" * 100, filesystems=only_dfs)


class TestEmptyRegistry:
    def test_no_filesystems_registered_yet(self):
        # In Phase A nothing registers on oaknut.filesystem.
        assert filesystem_names() == []

    def test_create_unknown_raises(self):
        with pytest.raises(FilesystemExtensionError):
            create_filesystem("nonexistent")
