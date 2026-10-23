"""Tests for filename metadata encoding/decoding."""

import pytest
from oaknut.file.filename_encoding import (
    build_filename_suffix,
    build_loadexec_filename_suffix,
    build_mos_filename_suffix,
    parse_encoded_filename,
)
from oaknut.file.meta import AcornMeta


class TestParseEncodedFilename:
    def test_filetype_suffix(self):
        clean, meta = parse_encoded_filename("HELLO,ffb")
        assert clean == "HELLO"
        assert meta is not None
        assert meta.infer_filetype() == 0xFFB

    def test_filetype_uppercase(self):
        clean, meta = parse_encoded_filename("HELLO,FFB")
        assert clean == "HELLO"
        assert meta.infer_filetype() == 0xFFB

    def test_fixed_width_comma_load_exec(self):
        """The ,llllllll,eeeeeeee form python-zipinfo-riscos writes still reads."""
        clean, meta = parse_encoded_filename("PROG,ffff0e10,0000801f")
        assert clean == "PROG"
        assert meta.load_address == 0xFFFF0E10
        assert meta.exec_address == 0x0000801F

    def test_hyphen_load_exec(self):
        clean, meta = parse_encoded_filename("PROG,1900-801f")
        assert clean == "PROG"
        assert meta.load_address == 0x1900
        assert meta.exec_address == 0x801F

    def test_no_encoding(self):
        clean, meta = parse_encoded_filename("HELLO")
        assert clean == "HELLO"
        assert meta is None

    def test_comma_in_name_no_match(self):
        clean, meta = parse_encoded_filename("FILE,xyz")
        # "xyz" is not valid hex for filetype
        assert meta is None

    def test_filetype_synthesises_load_address(self):
        """Filetype suffix synthesises a RISC OS load address."""
        _, meta = parse_encoded_filename("FILE,ffb")
        assert meta.is_filetype_stamped is True
        assert meta.infer_filetype() == 0xFFB


class TestBuildFilenameSuffix:
    def test_filetype_stamped(self):
        meta = AcornMeta(load_address=0xFFFFFB00, exec_address=0)
        suffix = build_filename_suffix(meta)
        assert suffix == ",ffb"

    def test_literal_load_exec(self):
        """Untyped files take the ,load-exec form RISC OS HostFS and LanManFS read."""
        meta = AcornMeta(load_address=0x1900, exec_address=0x8023)
        suffix = build_filename_suffix(meta)
        assert suffix == ",1900-8023"

    def test_literal_load_exec_full_width(self):
        meta = AcornMeta(load_address=0x12345678, exec_address=0x9ABCDEF0)
        assert build_filename_suffix(meta) == ",12345678-9abcdef0"


class TestBuildLoadexecFilenameSuffix:
    def test_basic(self):
        meta = AcornMeta(load_address=0x1900, exec_address=0x8023)
        suffix = build_loadexec_filename_suffix(meta)
        assert suffix == ",1900-8023"

    def test_no_zero_padding(self):
        meta = AcornMeta(load_address=0xFF, exec_address=0x0)
        suffix = build_loadexec_filename_suffix(meta)
        assert suffix == ",ff-0"

    def test_filetype_stamped_keeps_datestamp(self):
        meta = AcornMeta(load_address=0xFFFFFB12, exec_address=0x34567890)
        assert build_loadexec_filename_suffix(meta) == ",fffffb12-34567890"


class TestBuildMosFilenameSuffix:
    def test_deprecated_alias(self):
        meta = AcornMeta(load_address=0x1900, exec_address=0x8023)
        with pytest.deprecated_call():
            suffix = build_mos_filename_suffix(meta)
        assert suffix == ",1900-8023"


class TestFilenameEncodingRoundTrip:
    def test_filetype_round_trip(self):
        meta = AcornMeta(load_address=0xFFFFFB00, exec_address=0)
        suffix = build_filename_suffix(meta)
        clean, parsed = parse_encoded_filename(f"FILE{suffix}")
        assert clean == "FILE"
        assert parsed.infer_filetype() == 0xFFB

    def test_load_exec_round_trip(self):
        meta = AcornMeta(load_address=0x1900, exec_address=0x8023)
        suffix = build_filename_suffix(meta)
        clean, parsed = parse_encoded_filename(f"FILE{suffix}")
        assert parsed.load_address == 0x1900
        assert parsed.exec_address == 0x8023

    def test_loadexec_round_trip(self):
        meta = AcornMeta(load_address=0xFFFFFB12, exec_address=0x34567890)
        suffix = build_loadexec_filename_suffix(meta)
        clean, parsed = parse_encoded_filename(f"FILE{suffix}")
        assert clean == "FILE"
        assert parsed.load_address == 0xFFFFFB12
        assert parsed.exec_address == 0x34567890


class TestTypedMetadata:
    """``typed_metadata`` says whether the &FFF marker means a filetype."""

    def test_marker_reads_as_filetype_by_default(self):
        meta = AcornMeta(load_address=0xFFFF1900, exec_address=0xFFFF8023)
        assert build_filename_suffix(meta) == ",f19"

    def test_marker_kept_as_addresses_when_untyped(self):
        meta = AcornMeta(load_address=0xFFFF1900, exec_address=0xFFFF8023)
        assert build_filename_suffix(meta, typed_metadata=False) == ",ffff1900-ffff8023"

    def test_filetyped_file_keeps_its_words_when_untyped(self):
        meta = AcornMeta(load_address=0xFFFFFB12, exec_address=0x34567890)
        assert build_filename_suffix(meta, typed_metadata=False) == ",fffffb12-34567890"

    def test_plain_addresses_unaffected(self):
        meta = AcornMeta(load_address=0x1900, exec_address=0x8023)
        assert build_filename_suffix(meta, typed_metadata=False) == ",1900-8023"
