"""Tests for the DFS probers and their participation in the cascade.

These exercise the real entry-point discovery path: ``identify()`` must
find ``acorn_dfs`` because oaknut-dfs registers it, and content must win
over a misleading file extension.
"""

from oaknut.dfs.probers import AcornDFSProber
from oaknut.identify import Confidence, identify, prober_names, reader_for

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_ACORN_SSD = REFERENCE_IMAGES_DIRPATH / "01-basic-validation.ssd"
_DOUBLE_SIDED_DSD = REFERENCE_IMAGES_DIRPATH / "04-double-sided.dsd"


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
