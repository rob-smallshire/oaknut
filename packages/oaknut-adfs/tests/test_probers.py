"""Tests for the ADFS prober and its participation in the cascade."""

from oaknut.adfs import ADFS, ADFS_S
from oaknut.adfs.probers import ADFSProber
from oaknut.identify import Confidence, identify, prober_names, reader_for

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

# A real old-map ADFS hard disc (it also hosts an AFS tail partition).
_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"


class TestRegistration:
    def test_adfs_is_a_registered_prober(self):
        assert "adfs" in prober_names()


class TestADFSProber:
    def test_freshly_created_adfs_image_is_strong(self, tmp_path):
        image_filepath = tmp_path / "disc.ads"
        with ADFS.create_file(str(image_filepath), ADFS_S, title="TEST"):
            pass
        prober = ADFSProber(name="adfs")
        with reader_for(image_filepath) as reader:
            (ident,) = list(prober.probe(reader))
        # Both the directory signature and the map checksums hold.
        assert ident.family == "adfs"
        assert ident.confidence is Confidence.STRONG
        assert any("ADFS S" in line for line in ident.evidence)

    def test_probes_a_real_hard_disc(self):
        prober = ADFSProber(name="adfs")
        with reader_for(_L3FS_DAT) as reader:
            (ident,) = list(prober.probe(reader))
        assert ident.family == "adfs"
        assert ident.confidence is Confidence.STRONG
        assert any("Hugo" in line for line in ident.evidence)

    def test_rejects_blank_image(self):
        prober = ADFSProber(name="adfs")
        with reader_for(b"\x00" * 163840) as reader:
            assert list(prober.probe(reader)) == []

    def test_rejects_too_small_image(self):
        prober = ADFSProber(name="adfs")
        with reader_for(b"\x00" * 256) as reader:
            assert list(prober.probe(reader)) == []


class TestCascade:
    def test_combined_image_reports_both_adfs_and_afs(self):
        families = {c.family for c in identify(_L3FS_DAT)}
        assert {"adfs", "afs"} <= families

    def test_afs_outranks_adfs_on_a_combined_image(self):
        # AFS is CERTAIN (verified magic); ADFS is STRONG — so AFS leads.
        results = identify(_L3FS_DAT)
        assert results[0].family == "afs"
        assert any(c.family == "adfs" for c in results)
