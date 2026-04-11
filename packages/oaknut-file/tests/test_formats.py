"""Tests for MetaFormat enum and source labels."""

from oaknut.file.formats import (
    SOURCE_DIR,
    SOURCE_FILENAME,
    SOURCE_INF_PIEB,
    SOURCE_INF_TRAD,
    SOURCE_SPARKFS,
    MetaFormat,
)


class TestMetaFormat:
    def test_values(self):
        assert MetaFormat.INF_TRAD == "inf-trad"
        assert MetaFormat.INF_PIEB == "inf-pieb"
        assert MetaFormat.XATTR_ACORN == "xattr-acorn"
        assert MetaFormat.XATTR_PIEB == "xattr-pieb"
        assert MetaFormat.FILENAME_RISCOS == "filename-riscos"
        assert MetaFormat.FILENAME_MOS == "filename-mos"

    def test_xattr_variants_are_distinct(self):
        """The two xattr namespaces are distinct output formats."""
        assert MetaFormat.XATTR_ACORN != MetaFormat.XATTR_PIEB

    def test_is_string(self):
        assert isinstance(MetaFormat.INF_TRAD, str)


class TestSourceLabels:
    def test_labels_are_strings(self):
        for label in (
            SOURCE_SPARKFS,
            SOURCE_INF_TRAD,
            SOURCE_INF_PIEB,
            SOURCE_FILENAME,
            SOURCE_DIR,
        ):
            assert isinstance(label, str)

    def test_labels_are_distinct(self):
        labels = {SOURCE_SPARKFS, SOURCE_INF_TRAD, SOURCE_INF_PIEB, SOURCE_FILENAME, SOURCE_DIR}
        assert len(labels) == 5
