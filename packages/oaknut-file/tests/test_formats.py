"""Tests for MetaFormat enum and source labels."""

from oaknut_file.formats import (
    MetaFormat,
    SOURCE_SPARKFS,
    SOURCE_INF_TRAD,
    SOURCE_INF_PIEB,
    SOURCE_FILENAME,
    SOURCE_DIR,
)


class TestMetaFormat:

    def test_values(self):
        assert MetaFormat.INF_TRAD == "inf-trad"
        assert MetaFormat.INF_PIEB == "inf-pieb"
        assert MetaFormat.XATTR == "xattr"
        assert MetaFormat.FILENAME_RISCOS == "filename-riscos"
        assert MetaFormat.FILENAME_MOS == "filename-mos"

    def test_is_string(self):
        assert isinstance(MetaFormat.INF_TRAD, str)


class TestSourceLabels:

    def test_labels_are_strings(self):
        for label in (SOURCE_SPARKFS, SOURCE_INF_TRAD, SOURCE_INF_PIEB,
                      SOURCE_FILENAME, SOURCE_DIR):
            assert isinstance(label, str)

    def test_labels_are_distinct(self):
        labels = {SOURCE_SPARKFS, SOURCE_INF_TRAD, SOURCE_INF_PIEB,
                  SOURCE_FILENAME, SOURCE_DIR}
        assert len(labels) == 5
