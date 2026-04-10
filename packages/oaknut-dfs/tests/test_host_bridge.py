"""Tests for the host_bridge module — round-trip every MetaFormat.

These tests exercise the export/import cascade directly, independently
of DFS or ADFS. They verify that oaknut_file's INF, xattr, and
filename-encoded metadata schemes are all plumbed through.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from oaknut_file import Access, AcornMeta, MetaFormat

from oaknut_dfs.host_bridge import (
    DEFAULT_EXPORT_META_FORMAT,
    DEFAULT_IMPORT_META_FORMATS,
    export_with_metadata,
    import_with_metadata,
)


# --- Capability probe for xattr support ------------------------------------


def _xattr_supported(dirpath: Path) -> bool:
    """Return True if the filesystem at *dirpath* supports user xattrs."""
    probe = dirpath / ".oaknut_xattr_probe"
    probe.write_bytes(b"")
    try:
        if hasattr(os, "setxattr"):
            os.setxattr(str(probe), "user.oaknut.probe", b"1")
            return True
        try:
            import xattr
        except ImportError:
            return False
        xattr.xattr(str(probe)).set("user.oaknut.probe", b"1")
        return True
    except OSError:
        return False
    finally:
        probe.unlink(missing_ok=True)


@pytest.fixture
def xattr_tmp_path(tmp_path: Path) -> Path:
    if not _xattr_supported(tmp_path):
        pytest.skip("filesystem does not support user extended attributes")
    return tmp_path


# --- Sample metadata --------------------------------------------------------


SAMPLE_META = AcornMeta(
    load_addr=0x00001900,
    exec_addr=0x00008023,
    attr=int(Access.R | Access.W | Access.L),
)


FILETYPE_META = AcornMeta(
    load_addr=0xFFFFFD00,   # RISC OS filetype-stamped (filetype 0xFFD)
    exec_addr=0x00000000,
    attr=int(Access.R | Access.W),
)


# --- Defaults ---------------------------------------------------------------


def test_default_export_format_is_inf_trad():
    assert DEFAULT_EXPORT_META_FORMAT == MetaFormat.INF_TRAD


def test_default_import_cascade_prefers_inf_then_xattr_then_filename():
    assert DEFAULT_IMPORT_META_FORMATS[0] == MetaFormat.INF_TRAD
    assert MetaFormat.FILENAME_RISCOS in DEFAULT_IMPORT_META_FORMATS


# --- INF round-trip ---------------------------------------------------------


@pytest.mark.parametrize("fmt", [MetaFormat.INF_TRAD, MetaFormat.INF_PIEB])
def test_inf_round_trip(tmp_path: Path, fmt: MetaFormat):
    target = tmp_path / "HELLO"
    written = export_with_metadata(b"hello", target, SAMPLE_META, meta_format=fmt)

    assert written == target
    assert written.read_bytes() == b"hello"
    sidecar = tmp_path / "HELLO.inf"
    assert sidecar.exists(), "INF sidecar must be written next to data file"

    clean, source, meta = import_with_metadata(written, meta_formats=(fmt,))
    assert clean == written
    assert source in ("inf-trad", "inf-pieb")
    assert meta.load_addr == SAMPLE_META.load_addr
    assert meta.exec_addr == SAMPLE_META.exec_addr
    assert meta.attr == SAMPLE_META.attr


def test_inf_sidecar_name_is_fixed(tmp_path: Path):
    """Sidecar is always <datafile>.inf — appending .inf, not replacing."""
    target = tmp_path / "PROG.bin"
    export_with_metadata(b"x", target, SAMPLE_META, meta_format=MetaFormat.INF_TRAD)
    assert (tmp_path / "PROG.bin.inf").exists()
    assert not (tmp_path / "PROG.inf").exists()


def test_inf_pieb_on_import_accepts_trad_sidecar(tmp_path: Path):
    """INF_PIEB in the cascade still picks up a traditional .inf, because
    oaknut-file's parser auto-detects the dialect."""
    target = tmp_path / "FOO"
    export_with_metadata(b"data", target, SAMPLE_META, meta_format=MetaFormat.INF_TRAD)

    _, source, meta = import_with_metadata(
        target, meta_formats=(MetaFormat.INF_PIEB,),
    )
    assert source == "inf-trad"
    assert meta.load_addr == SAMPLE_META.load_addr


# --- Xattr round-trip -------------------------------------------------------


@pytest.mark.parametrize(
    "fmt",
    [MetaFormat.XATTR_ACORN, MetaFormat.XATTR_PIEB],
)
def test_xattr_round_trip(xattr_tmp_path: Path, fmt: MetaFormat):
    target = xattr_tmp_path / "DATA"
    export_with_metadata(b"abc", target, SAMPLE_META, meta_format=fmt)

    # No sidecar should be produced by xattr formats
    assert not (xattr_tmp_path / "DATA.inf").exists()

    clean, source, meta = import_with_metadata(target, meta_formats=(fmt,))
    assert clean == target
    assert source == fmt.value
    assert meta.load_addr == SAMPLE_META.load_addr
    assert meta.exec_addr == SAMPLE_META.exec_addr
    assert meta.attr == SAMPLE_META.attr


# --- Filename-encoded round-trip --------------------------------------------


@pytest.mark.parametrize(
    "fmt",
    [MetaFormat.FILENAME_RISCOS, MetaFormat.FILENAME_MOS],
)
def test_filename_round_trip(tmp_path: Path, fmt: MetaFormat):
    target = tmp_path / "PROG"
    written = export_with_metadata(
        b"xyz", target, SAMPLE_META, meta_format=fmt,
    )

    # The write path was rewritten with a suffix
    assert written.parent == tmp_path
    assert written.name.startswith("PROG,")
    assert written.read_bytes() == b"xyz"
    assert not (tmp_path / "PROG").exists()

    clean, source, meta = import_with_metadata(written, meta_formats=(fmt,))
    assert clean == tmp_path / "PROG"  # suffix stripped
    assert source == "filename"
    assert meta.load_addr == SAMPLE_META.load_addr
    assert meta.exec_addr == SAMPLE_META.exec_addr


def test_filename_riscos_filetype_stamped(tmp_path: Path):
    """Filetype-stamped files use the ,xxx suffix form."""
    target = tmp_path / "DOC"
    written = export_with_metadata(
        b"text", target, FILETYPE_META, meta_format=MetaFormat.FILENAME_RISCOS,
    )
    assert written.name == "DOC,ffd"


# --- None: data only -------------------------------------------------------


def test_meta_format_none_writes_only_data(tmp_path: Path):
    target = tmp_path / "BARE"
    written = export_with_metadata(b"raw", target, SAMPLE_META, meta_format=None)
    assert written == target
    assert target.read_bytes() == b"raw"
    assert not (tmp_path / "BARE.inf").exists()


# --- Import cascade behaviour ----------------------------------------------


def test_import_cascade_respects_user_order(tmp_path: Path):
    """A source file with both an INF sidecar and a filename-encoded
    suffix resolves via whichever the user lists first in meta_formats."""
    target = tmp_path / "FOO"
    # Write with INF first — but then rename to add a filename suffix too.
    export_with_metadata(b"data", target, SAMPLE_META, meta_format=MetaFormat.INF_TRAD)
    suffixed = tmp_path / "FOO,00001900,00008023"
    target.rename(suffixed)
    # Move sidecar alongside the suffixed path so INF lookup works.
    (tmp_path / "FOO.inf").rename(tmp_path / "FOO,00001900,00008023.inf")

    # Cascade prefers INF
    _, source_inf, _ = import_with_metadata(
        suffixed, meta_formats=(MetaFormat.INF_TRAD, MetaFormat.FILENAME_RISCOS),
    )
    assert source_inf == "inf-trad"

    # Cascade prefers filename
    _, source_fn, _ = import_with_metadata(
        suffixed, meta_formats=(MetaFormat.FILENAME_RISCOS, MetaFormat.INF_TRAD),
    )
    assert source_fn == "filename"


def test_import_empty_cascade_returns_no_metadata(tmp_path: Path):
    target = tmp_path / "PLAIN"
    target.write_bytes(b"x")
    clean, source, meta = import_with_metadata(target, meta_formats=())
    assert clean == target
    assert source is None
    assert meta.load_addr is None
    assert meta.exec_addr is None
    assert meta.attr is None


def test_import_no_metadata_present(tmp_path: Path):
    """A plain file with the default cascade but no metadata returns None."""
    target = tmp_path / "PLAIN"
    target.write_bytes(b"x")
    clean, source, meta = import_with_metadata(target)
    assert clean == target
    assert source is None
    assert not meta.has_metadata


def test_import_default_cascade_finds_inf(tmp_path: Path):
    target = tmp_path / "FILE"
    export_with_metadata(b"d", target, SAMPLE_META, meta_format=MetaFormat.INF_TRAD)
    _, source, meta = import_with_metadata(target)
    assert source == "inf-trad"
    assert meta.load_addr == SAMPLE_META.load_addr
