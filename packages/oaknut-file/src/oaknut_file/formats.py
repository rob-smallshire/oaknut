"""Metadata format and source labels.

``MetaFormat`` enumerates the output formats for writing file metadata
to the host filesystem. The ``SOURCE_*`` constants label where
metadata was obtained from.
"""

from __future__ import annotations

from enum import Enum


class MetaFormat(str, Enum):
    """Supported metadata output formats."""

    INF_TRAD = "inf-trad"
    INF_PIEB = "inf-pieb"
    XATTR = "xattr"
    FILENAME_RISCOS = "filename-riscos"
    FILENAME_MOS = "filename-mos"


SOURCE_SPARKFS = "sparkfs"
SOURCE_INF_TRAD = "inf-trad"
SOURCE_INF_PIEB = "inf-pieb"
SOURCE_FILENAME = "filename"
SOURCE_DIR = "dir"
