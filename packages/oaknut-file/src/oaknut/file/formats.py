"""Metadata format and source labels.

``MetaFormat`` enumerates the output formats for writing file metadata
to the host filesystem. The ``SOURCE_*`` constants label where
metadata was obtained from.
"""

from __future__ import annotations

import warnings
from enum import Enum


class MetaFormat(str, Enum):
    """Supported metadata output formats.

    ``FILENAME_MOS`` is a deprecated alias for ``FILENAME_LOADEXEC``, and
    ``MetaFormat("filename-mos")`` resolves to it with a
    :class:`DeprecationWarning`.
    """

    INF_TRAD = "inf-trad"
    INF_PIEB = "inf-pieb"
    XATTR_ACORN = "xattr-acorn"
    XATTR_PIEB = "xattr-pieb"
    FILENAME_RISCOS = "filename-riscos"
    FILENAME_LOADEXEC = "filename-loadexec"
    FILENAME_MOS = "filename-loadexec"

    @classmethod
    def _missing_(cls, value):
        replacement = DEPRECATED_META_FORMATS.get(value)
        if replacement is None:
            return None
        warnings.warn(
            f"meta format {value!r} is deprecated; use {replacement.value!r}.",
            DeprecationWarning,
            stacklevel=2,
        )
        return replacement


#: Retired format names, mapped to the format each now names.
DEPRECATED_META_FORMATS: dict[str, MetaFormat] = {
    "filename-mos": MetaFormat.FILENAME_LOADEXEC,
}


SOURCE_SPARKFS = "sparkfs"
SOURCE_INF_TRAD = "inf-trad"
SOURCE_INF_PIEB = "inf-pieb"
SOURCE_FILENAME = "filename"
SOURCE_DIR = "dir"
