"""Bridge between Acorn filesystem images and the host filesystem.

Centralises all contact with ``oaknut_file`` for import/export of files
to/from DFS and ADFS disc images. Both ``DFSPath`` and ``ADFSPath``
delegate here so that widening the set of supported metadata schemes
is a single-file change.

Two schemes are modelled, mirroring ``oaknut_zip``:

- **Export** takes one :class:`~oaknut_file.MetaFormat` (or ``None`` for
  data-only). The chosen format determines where the metadata lands —
  traditional or PiEconetBridge INF sidecar, xattr on the data file,
  or a RISC OS / MOS filename suffix.
- **Import** takes an ordered sequence of :class:`~oaknut_file.MetaFormat`
  values and tries each reader in turn, returning the first hit.
  ``DEFAULT_IMPORT_META_FORMATS`` is a sensible cascade that most
  callers won't need to override.

The ``.inf`` sidecar convention is fixed: the sidecar for data file
``foo.bin`` is always ``foo.bin.inf``. There is no API for specifying
a different sidecar name on either side.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from oaknut_file import (
    AcornMeta,
    MetaFormat,
    SOURCE_FILENAME,
    build_filename_suffix,
    build_mos_filename_suffix,
    format_pieb_inf_line,
    format_trad_inf_line,
    parse_encoded_filename,
    read_acorn_xattrs,
    read_econet_xattrs,
    read_inf_file,
    write_acorn_xattrs,
    write_econet_xattrs,
    write_inf_file,
)


# Xattr source labels — oaknut_file doesn't (yet) define these, so we
# use the MetaFormat value strings directly. If oaknut_file later grows
# SOURCE_XATTR_* constants, swap these for them.
SOURCE_XATTR_ACORN = MetaFormat.XATTR_ACORN.value
SOURCE_XATTR_PIEB = MetaFormat.XATTR_PIEB.value


DEFAULT_EXPORT_META_FORMAT: MetaFormat | None = MetaFormat.INF_TRAD


# Default import cascade. Ordered from most authoritative / most common
# to least. ``XATTR_PIEB`` is deliberately omitted because
# ``read_acorn_xattrs`` internally falls back to the Econet namespace,
# so a dedicated PiEB entry here would be unreachable. Callers that
# want to distinguish the two on import should list ``XATTR_PIEB``
# explicitly *before* ``XATTR_ACORN``.
DEFAULT_IMPORT_META_FORMATS: tuple[MetaFormat, ...] = (
    MetaFormat.INF_TRAD,
    MetaFormat.XATTR_ACORN,
    MetaFormat.FILENAME_RISCOS,
)


def _sidecar_filepath(data_filepath: Path) -> Path:
    """Return the fixed INF sidecar path for *data_filepath*.

    Convention: append ``.inf`` to the full data filename. So
    ``foo.bin`` → ``foo.bin.inf``. Matches the existing oaknut-dfs
    convention and oaknut-zip's ``.inf`` resolution.
    """
    return data_filepath.with_suffix(data_filepath.suffix + ".inf")


def _attr_of(meta: AcornMeta) -> int | None:
    return meta.attr


# --- Export ---------------------------------------------------------------


def export_with_metadata(
    data: bytes,
    target_filepath: Path,
    meta: AcornMeta,
    *,
    meta_format: MetaFormat | None = DEFAULT_EXPORT_META_FORMAT,
    owner: int = 0,
    filename: str | None = None,
) -> Path:
    """Write *data* to *target_filepath* and emit metadata.

    Args:
        data: Raw file contents.
        target_filepath: Destination on the host. Parent directories
            are created if missing.
        meta: Metadata for the file.
        meta_format: How to emit metadata. ``None`` writes only the
            data, no sidecar, no xattr, no filename rewriting.
        owner: Econet owner ID, used only by PiEconetBridge formats
            (``INF_PIEB`` and ``XATTR_PIEB``); ignored otherwise.
        filename: Acorn-native filename to record in traditional INF
            sidecars (e.g. ``"$.HELLO"`` or ``"Games.Elite"``). Used
            only by ``MetaFormat.INF_TRAD``, which is the only format
            with a filename field. When omitted, the host filename is
            used.

    Returns:
        The path that was actually written. For filename-encoded
        formats this differs from *target_filepath* because a suffix
        has been appended.
    """
    target_filepath = Path(target_filepath)
    target_filepath.parent.mkdir(parents=True, exist_ok=True)

    load_addr = meta.load_addr or 0
    exec_addr = meta.exec_addr or 0
    attr = _attr_of(meta)

    if meta_format is None:
        target_filepath.write_bytes(data)
        return target_filepath

    if meta_format == MetaFormat.INF_TRAD:
        target_filepath.write_bytes(data)
        line = format_trad_inf_line(
            filename=filename if filename is not None else target_filepath.name,
            load_addr=load_addr,
            exec_addr=exec_addr,
            length=len(data),
            attr=attr,
        )
        write_inf_file(_sidecar_filepath(target_filepath), line)
        return target_filepath

    if meta_format == MetaFormat.INF_PIEB:
        target_filepath.write_bytes(data)
        line = format_pieb_inf_line(
            load_addr=load_addr,
            exec_addr=exec_addr,
            attr=attr,
            owner=owner,
        )
        write_inf_file(_sidecar_filepath(target_filepath), line)
        return target_filepath

    if meta_format == MetaFormat.XATTR_ACORN:
        target_filepath.write_bytes(data)
        try:
            write_acorn_xattrs(
                target_filepath,
                load_addr=load_addr,
                exec_addr=exec_addr,
                attr=attr,
            )
        except (OSError, ImportError):
            target_filepath.unlink(missing_ok=True)
            raise
        return target_filepath

    if meta_format == MetaFormat.XATTR_PIEB:
        target_filepath.write_bytes(data)
        try:
            write_econet_xattrs(
                target_filepath,
                load_addr=load_addr,
                exec_addr=exec_addr,
                attr=attr,
                owner=owner,
            )
        except (OSError, ImportError):
            target_filepath.unlink(missing_ok=True)
            raise
        return target_filepath

    if meta_format == MetaFormat.FILENAME_RISCOS:
        suffix = build_filename_suffix(meta)
        encoded_filepath = target_filepath.with_name(target_filepath.name + suffix)
        encoded_filepath.write_bytes(data)
        return encoded_filepath

    if meta_format == MetaFormat.FILENAME_MOS:
        suffix = build_mos_filename_suffix(meta)
        encoded_filepath = target_filepath.with_name(target_filepath.name + suffix)
        encoded_filepath.write_bytes(data)
        return encoded_filepath

    raise ValueError(f"Unsupported MetaFormat: {meta_format!r}")


# --- Import ---------------------------------------------------------------


def _try_inf(source_filepath: Path) -> tuple[Path, str, AcornMeta] | None:
    sidecar = _sidecar_filepath(source_filepath)
    result = read_inf_file(sidecar)
    if result is None:
        return None
    source_label, meta = result
    return source_filepath, source_label, meta


def _try_xattr_acorn(source_filepath: Path) -> tuple[Path, str, AcornMeta] | None:
    try:
        meta = read_acorn_xattrs(source_filepath)
    except (OSError, ImportError):
        return None
    if meta is None:
        return None
    return source_filepath, SOURCE_XATTR_ACORN, meta


def _try_xattr_pieb(source_filepath: Path) -> tuple[Path, str, AcornMeta] | None:
    try:
        meta = read_econet_xattrs(source_filepath)
    except (OSError, ImportError):
        return None
    if meta is None:
        return None
    return source_filepath, SOURCE_XATTR_PIEB, meta


def _try_filename(source_filepath: Path) -> tuple[Path, str, AcornMeta] | None:
    clean_name, meta = parse_encoded_filename(source_filepath.name)
    if meta is None:
        return None
    clean_filepath = source_filepath.with_name(clean_name)
    return clean_filepath, SOURCE_FILENAME, meta


_IMPORT_READERS = {
    MetaFormat.INF_TRAD: _try_inf,
    MetaFormat.INF_PIEB: _try_inf,
    MetaFormat.XATTR_ACORN: _try_xattr_acorn,
    MetaFormat.XATTR_PIEB: _try_xattr_pieb,
    MetaFormat.FILENAME_RISCOS: _try_filename,
    MetaFormat.FILENAME_MOS: _try_filename,
}


def import_with_metadata(
    source_filepath: Path,
    *,
    meta_formats: Sequence[MetaFormat] = DEFAULT_IMPORT_META_FORMATS,
) -> tuple[Path, str | None, AcornMeta]:
    """Resolve metadata for a host file by trying readers in order.

    Args:
        source_filepath: The host data file.
        meta_formats: Ordered cascade of metadata schemes to try.
            First hit wins.

    Returns:
        ``(clean_source_path, source_label, meta)``.

        * ``clean_source_path`` equals *source_filepath* unless the
          filename-encoded reader matched, in which case the encoded
          suffix has been stripped.
        * ``source_label`` is one of oaknut_file's ``SOURCE_*``
          constants, ``"xattr-acorn"`` / ``"xattr-pieb"``, or ``None``
          if no reader matched.
        * ``meta`` is the resolved :class:`AcornMeta`, or an empty
          ``AcornMeta()`` when no reader matched.

    The dialect-equivalent pairs (``INF_TRAD``/``INF_PIEB`` and
    ``FILENAME_RISCOS``/``FILENAME_MOS``) dispatch to the same reader;
    oaknut_file's parsers auto-detect the dialect, so listing both is
    harmless but redundant.
    """
    source_filepath = Path(source_filepath)
    for fmt in meta_formats:
        reader = _IMPORT_READERS.get(fmt)
        if reader is None:
            continue
        hit = reader(source_filepath)
        if hit is not None:
            return hit
    return source_filepath, None, AcornMeta()
