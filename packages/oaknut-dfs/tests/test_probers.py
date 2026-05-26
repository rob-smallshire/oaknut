"""Tests for the DFS probers and their participation in the cascade.

These exercise the real entry-point discovery path: ``identify()`` must
find ``acorn_dfs`` because oaknut-dfs registers it, and content must win
over a misleading file extension.
"""

from oaknut.dfs.probers import AcornDFSProber, WatfordDFSProber
from oaknut.identify import Confidence, identify, prober_names, reader_for

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_ACORN_SSD = REFERENCE_IMAGES_DIRPATH / "01-basic-validation.ssd"
_DOUBLE_SIDED_DSD = REFERENCE_IMAGES_DIRPATH / "04-double-sided.dsd"


def _watford_image_bytes() -> bytes:
    """A minimal but valid Watford DDFS image (80-track single-sided).

    Mirrors the hand-crafted layout the catalogue's own tests use: the
    0xAA marker in sector 2 and metadata synced across both catalogue
    sections, which is what WatfordDFSCatalogue.matches keys on.
    """
    buffer = bytearray(204800)
    buffer[0:10] = b"WATFORD   "  # section-1 title
    buffer[256 + 6] = 0x03  # boot option 0, total-sectors high bits
    buffer[256 + 7] = 0x20  # total-sectors low byte (0x320 = 800)
    buffer[512:524] = b"\xaa" * 12  # sector 2: Watford signature
    buffer[768 + 6] = 0x03  # section-2 metadata mirrors section 1
    buffer[768 + 7] = 0x20
    return bytes(buffer)


class TestRegistration:
    def test_acorn_dfs_is_a_registered_prober(self):
        # The entry point in pyproject.toml must be discoverable.
        assert "acorn_dfs" in prober_names()


class TestAcornDFSProber:
    def test_probes_a_real_dfs_image(self):
        prober = AcornDFSProber(name="acorn_dfs")
        with reader_for(_ACORN_SSD) as reader:
            results = list(prober.probe(reader))
        assert len(results) == 1
        (ident,) = results
        assert ident.family == "dfs"
        assert ident.prober_name == "acorn_dfs"
        assert ident.confidence is Confidence.PROBABLE
        assert ident.evidence  # a non-empty reason was given

    def test_double_sided_image_recognised_as_dfs(self):
        prober = AcornDFSProber(name="acorn_dfs")
        with reader_for(_DOUBLE_SIDED_DSD) as reader:
            results = list(prober.probe(reader))
        assert [r.family for r in results] == ["dfs"]

    def test_rejects_blank_image(self):
        prober = AcornDFSProber(name="acorn_dfs")
        with reader_for(b"\x00" * 204800, suffix_hint=".ssd") as reader:
            assert list(prober.probe(reader)) == []

    def test_rejects_too_small_image(self):
        prober = AcornDFSProber(name="acorn_dfs")
        with reader_for(b"\x00" * 256) as reader:
            assert list(prober.probe(reader)) == []


class TestCascade:
    def test_identify_finds_dfs_in_a_real_image(self):
        results = identify(_ACORN_SSD)
        assert results, "expected at least one identification"
        top = results[0]
        assert top.family == "dfs"
        assert top.prober_name == "acorn_dfs"

    def test_content_wins_over_a_misleading_extension(self):
        # Same DFS bytes presented under an ADFS-ish extension: content
        # identification must not be fooled by the name.
        data = _ACORN_SSD.read_bytes()
        results = identify(data, suffix_hint=".adf")
        assert any(r.family == "dfs" for r in results)


class TestWatfordDFSProber:
    def test_watford_dfs_is_a_registered_prober(self):
        assert "watford_dfs" in prober_names()

    def test_probes_a_watford_image(self):
        prober = WatfordDFSProber(name="watford_dfs")
        with reader_for(_watford_image_bytes()) as reader:
            (ident,) = list(prober.probe(reader))
        assert ident.family == "dfs"
        assert ident.confidence is Confidence.STRONG

    def test_acorn_prober_excludes_watford(self):
        # The two DFS probers are mutually exclusive: Acorn's matcher
        # rejects the extended catalogue Watford's marker announces.
        prober = AcornDFSProber(name="acorn_dfs")
        with reader_for(_watford_image_bytes()) as reader:
            assert list(prober.probe(reader)) == []

    def test_cascade_prefers_watford_over_acorn_for_watford_image(self):
        results = identify(_watford_image_bytes(), suffix_hint=".ssd")
        assert results[0].prober_name == "watford_dfs"
        assert results[0].confidence is Confidence.STRONG
