"""Tests for the ZIP prober and its participation in the cascade."""

import zipfile

from oaknut.identify import Confidence, identify, prober_names, reader_for
from oaknut.zip.probers import ZipProber


class TestRegistration:
    def test_zip_is_a_registered_prober(self):
        assert "zip" in prober_names()


class TestZipProber:
    def test_archive_containing_a_file(self, tmp_path):
        archive_filepath = tmp_path / "data.zip"
        with zipfile.ZipFile(archive_filepath, "w") as archive:
            archive.writestr("hello.txt", "hi")
        prober = ZipProber(name="zip")
        with reader_for(archive_filepath) as reader:
            (ident,) = list(prober.probe(reader))
        assert ident.family == "zip"
        assert ident.confidence is Confidence.CERTAIN
        assert "local file header" in ident.evidence[0]

    def test_empty_archive(self, tmp_path):
        archive_filepath = tmp_path / "empty.zip"
        with zipfile.ZipFile(archive_filepath, "w"):
            pass
        prober = ZipProber(name="zip")
        with reader_for(archive_filepath) as reader:
            (ident,) = list(prober.probe(reader))
        assert "empty archive" in ident.evidence[0]

    def test_rejects_non_zip(self):
        prober = ZipProber(name="zip")
        with reader_for(b"this is plainly not a zip archive") as reader:
            assert list(prober.probe(reader)) == []


class TestCascade:
    def test_identify_finds_zip(self, tmp_path):
        archive_filepath = tmp_path / "data.zip"
        with zipfile.ZipFile(archive_filepath, "w") as archive:
            archive.writestr("x", "y")
        results = identify(archive_filepath)
        assert results[0].family == "zip"
        assert results[0].confidence is Confidence.CERTAIN
