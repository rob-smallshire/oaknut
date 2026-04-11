"""Tests for filename metadata encoding/decoding."""

import pytest

from oaknut.file.filename_encoding import (
    parse_encoded_filename,
    build_filename_suffix,
    build_mos_filename_suffix,
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

    def test_riscos_load_exec(self):
        clean, meta = parse_encoded_filename("PROG,ffff0e10,0000801f")
        assert clean == "PROG"
        assert meta.load_addr == 0xFFFF0E10
        assert meta.exec_addr == 0x0000801F

    def test_mos_load_exec(self):
        clean, meta = parse_encoded_filename("PROG,1900-801f")
        assert clean == "PROG"
        assert meta.load_addr == 0x1900
        assert meta.exec_addr == 0x801F

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
        meta = AcornMeta(load_addr=0xFFFFFB00, exec_addr=0)
        suffix = build_filename_suffix(meta)
        assert suffix == ",ffb"

    def test_literal_load_exec(self):
        meta = AcornMeta(load_addr=0x1900, exec_addr=0x8023)
        suffix = build_filename_suffix(meta)
        assert suffix == ",00001900,00008023"


class TestBuildMosFilenameSuffix:

    def test_basic(self):
        meta = AcornMeta(load_addr=0x1900, exec_addr=0x8023)
        suffix = build_mos_filename_suffix(meta)
        assert suffix == ",1900-8023"

    def test_no_zero_padding(self):
        meta = AcornMeta(load_addr=0xFF, exec_addr=0x0)
        suffix = build_mos_filename_suffix(meta)
        assert suffix == ",ff-0"


class TestFilenameEncodingRoundTrip:

    def test_filetype_round_trip(self):
        meta = AcornMeta(load_addr=0xFFFFFB00, exec_addr=0)
        suffix = build_filename_suffix(meta)
        clean, parsed = parse_encoded_filename(f"FILE{suffix}")
        assert clean == "FILE"
        assert parsed.infer_filetype() == 0xFFB

    def test_load_exec_round_trip(self):
        meta = AcornMeta(load_addr=0x1900, exec_addr=0x8023)
        suffix = build_filename_suffix(meta)
        clean, parsed = parse_encoded_filename(f"FILE{suffix}")
        assert parsed.load_addr == 0x1900
        assert parsed.exec_addr == 0x8023

    def test_mos_round_trip(self):
        meta = AcornMeta(load_addr=0x1900, exec_addr=0x8023)
        suffix = build_mos_filename_suffix(meta)
        clean, parsed = parse_encoded_filename(f"FILE{suffix}")
        assert parsed.load_addr == 0x1900
        assert parsed.exec_addr == 0x8023
