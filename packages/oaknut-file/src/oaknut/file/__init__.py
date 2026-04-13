"""Acorn file metadata handling.

Shared metadata layer for the oaknut package family: INF sidecar
parsing/formatting, filename encoding schemes, extended attributes,
and access flag management.
"""

__version__ = "10.0.5"

# Side-effect import registers the 'acorn' text codec on package import.
import oaknut.file.acorn_encoding  # noqa: F401
from oaknut.file.access import Access, format_access_hex, format_access_text, parse_access
from oaknut.file.boot_option import BootOption
from oaknut.file.copy import copy_file
from oaknut.file.exceptions import FSError
from oaknut.file.filename_encoding import (
    build_filename_suffix,
    build_mos_filename_suffix,
    parse_encoded_filename,
)
from oaknut.file.formats import (
    SOURCE_DIR,
    SOURCE_FILENAME,
    SOURCE_INF_PIEB,
    SOURCE_INF_TRAD,
    SOURCE_SPARKFS,
    MetaFormat,
)
from oaknut.file.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    SOURCE_XATTR_ACORN,
    SOURCE_XATTR_PIEB,
    export_with_metadata,
    import_with_metadata,
)
from oaknut.file.inf import (
    format_pieb_inf_line,
    format_trad_inf_line,
    parse_inf_line,
    read_inf_file,
    write_inf_file,
)
from oaknut.file.meta import AcornMeta
from oaknut.file.xattr import (
    read_acorn_xattrs,
    read_econet_xattrs,
    write_acorn_xattrs,
    write_econet_xattrs,
)

__all__ = [
    "Access",
    "AcornMeta",
    "copy_file",
    "BootOption",
    "DEFAULT_EXPORT_META_FORMAT",
    "DEFAULT_IMPORT_META_FORMATS",
    "FSError",
    "MetaFormat",
    "SOURCE_DIR",
    "SOURCE_FILENAME",
    "SOURCE_INF_PIEB",
    "SOURCE_INF_TRAD",
    "SOURCE_SPARKFS",
    "SOURCE_XATTR_ACORN",
    "SOURCE_XATTR_PIEB",
    "export_with_metadata",
    "import_with_metadata",
    "build_filename_suffix",
    "build_mos_filename_suffix",
    "format_access_hex",
    "format_access_text",
    "parse_access",
    "format_pieb_inf_line",
    "format_trad_inf_line",
    "parse_encoded_filename",
    "parse_inf_line",
    "read_acorn_xattrs",
    "read_econet_xattrs",
    "read_inf_file",
    "write_acorn_xattrs",
    "write_econet_xattrs",
    "write_inf_file",
]
