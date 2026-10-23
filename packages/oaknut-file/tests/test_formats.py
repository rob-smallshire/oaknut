"""Tests for MetaFormat enum and source labels."""

import pytest
from oaknut.file.formats import (
    DEPRECATED_META_FORMATS,
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
        assert MetaFormat.FILENAME_LOADEXEC == "filename-loadexec"

    def test_filename_mos_is_deprecated_alias(self):
        """The old filename-mos name resolves to filename-loadexec."""
        assert MetaFormat.FILENAME_MOS is MetaFormat.FILENAME_LOADEXEC
        with pytest.deprecated_call():
            assert MetaFormat("filename-mos") is MetaFormat.FILENAME_LOADEXEC

    def test_deprecated_names_not_iterated(self):
        assert "filename-mos" not in [f.value for f in MetaFormat]

    def test_deprecated_meta_formats(self):
        assert DEPRECATED_META_FORMATS == {"filename-mos": MetaFormat.FILENAME_LOADEXEC}

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
