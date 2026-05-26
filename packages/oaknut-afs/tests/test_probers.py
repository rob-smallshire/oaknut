"""Tests for the AFS prober and its participation in the cascade."""

from oaknut.afs.probers import AFSProber
from oaknut.identify import Confidence, identify, prober_names, reader_for

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

# A real old-map ADFS hard disc with an AFS tail partition: two
# sector-aligned AFS0 info sectors that are each other's redundant copy.
_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"


def _first_aligned_afs0(data: bytes) -> int:
    """Offset of the first sector-aligned AFS0 magic, or -1."""
    pos = data.find(b"AFS0")
    while pos != -1:
        if pos % 256 == 0:
            return pos
        pos = data.find(b"AFS0", pos + 1)
    return -1


def _afs_info_sector() -> bytes:
    """One genuine 256-byte AFS info sector, lifted from the l3fs image."""
    data = _L3FS_DAT.read_bytes()
    offset = _first_aligned_afs0(data)
    assert offset != -1
    return data[offset : offset + 256]


class TestRegistration:
    def test_afs_is_a_registered_prober(self):
        assert "afs" in prober_names()


class TestAFSProber:
    def test_real_image_with_verified_redundant_copy_is_certain(self):
        prober = AFSProber(name="afs")
        with reader_for(_L3FS_DAT) as reader:
            (ident,) = list(prober.probe(reader))
        assert ident.family == "afs"
        assert ident.confidence is Confidence.CERTAIN
        assert any("redundant copy verified" in line for line in ident.evidence)

    def test_single_unverified_copy_is_strong(self):
        # One valid info sector with no matching redundant copy: still a
        # real AFS magic, but unverified, so STRONG rather than CERTAIN.
        buffer = bytearray(4096)
        buffer[0:256] = _afs_info_sector()
        prober = AFSProber(name="afs")
        with reader_for(bytes(buffer)) as reader:
            (ident,) = list(prober.probe(reader))
        assert ident.confidence is Confidence.STRONG

    def test_unaligned_magic_is_ignored(self):
        # AFS0 that isn't at a sector boundary is file content, not an
        # info sector — the prober must not be fooled.
        buffer = bytearray(4096)
        buffer[128:128 + 256] = _afs_info_sector()
        prober = AFSProber(name="afs")
        with reader_for(bytes(buffer)) as reader:
            assert list(prober.probe(reader)) == []

    def test_rejects_non_afs_image(self):
        prober = AFSProber(name="afs")
        with reader_for(b"\x00" * 4096) as reader:
            assert list(prober.probe(reader)) == []


class TestCascade:
    def test_identify_leads_with_afs_on_a_combined_image(self):
        results = identify(_L3FS_DAT)
        assert results[0].family == "afs"
        assert results[0].confidence is Confidence.CERTAIN
