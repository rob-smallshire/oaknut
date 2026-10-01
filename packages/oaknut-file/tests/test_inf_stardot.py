"""Traditional INF files per the Stardot INF format specification (#71).

Test vectors from Tom Seddon's draft specification,
https://github.com/stardot/inf_format/blob/main/inf_format_full.md, with
J.G. Harston's choices (https://mdfs.net/Docs/Comp/BBC/Filing/Metadata)
where the specification leaves latitude or is silent:

- a lock marker (``Locked``, ``LOCKED``, a bare ``L``) means ``&19``;
- an omitted access field means ``&33``;
- an omitted exec address is the load address.

Symbolic access in an INF file is case-sensitive, as the specification
defines (upper case = owner, lower case = others). oaknut's own
``owner/public`` slash form is also accepted, case-insensitively, as in
the CLI.
"""

from __future__ import annotations

import pytest
from oaknut.file.inf import format_trad_inf_line, parse_inf_line, read_inf_file


def _meta(line: str):
    result = parse_inf_line(line)
    assert result is not None, line
    source, meta = result
    assert source == "inf-trad", line
    return meta


# -- Syntax 1: hex fields, the fourth of which may be an access field --


class TestSyntax1:
    def test_full_line(self):
        meta = _meta("$.ELITE FFFF0E00 FFFF8023 00001000 19")
        assert meta.name == "$.ELITE"
        assert (meta.load_address, meta.exec_address, meta.access) == (0xFFFF0E00, 0xFFFF8023, 0x19)

    def test_harston_extended_hex_fields(self):
        meta = _meta("MyFileName FFFF1900 FFFF8023 00001273 33 7B23 123106 7B20 112708 0100 0040")
        assert meta.access == 0x33

    def test_lower_case_hex(self):
        meta = _meta("$.F ffff1900 ffff8023 00000100 1b")
        assert (meta.load_address, meta.access) == (0xFFFF1900, 0x1B)

    def test_fields_drop_from_the_right(self):
        assert _meta("$.F FFFF1900 FFFF8023 00000100").access == 0x33
        meta = _meta("$.F FFFF1900 FFFF8023")
        assert (meta.exec_address, meta.access) == (0xFFFF8023, 0x33)

    def test_the_basic_line_is_name_load_exec(self):
        meta = _meta("$.DCONV 1900 801F")
        assert (meta.name, meta.load_address, meta.exec_address) == ("$.DCONV", 0x1900, 0x801F)

    def test_a_missing_exec_is_the_load_address(self):
        assert _meta("$.DATA 3000").exec_address == 0x3000


# -- The access field --


class TestAccessField:
    @pytest.mark.parametrize(
        ("field", "access"),
        [
            # Case-sensitive symbolic access: upper case owner, lower case others.
            ("WR", 0x03),
            ("WRr", 0x13),
            ("WRwr", 0x33),
            ("LWR", 0x0B),
            ("LRr", 0x19),
            ("LWRlr", 0x9B),
            ("e", 0x40),
            # D marks a directory and has no access bit.
            ("DLR", 0x09),
            ("dlr", 0x90),
            # A lone E or D is access, not hex.
            ("E", 0x04),
            ("D", 0x00),
            # Otherwise anything that looks like hex is hex.
            ("DE", 0xDE),
            ("ED", 0xED),
            ("19", 0x19),
            # oaknut's owner/public slash form, case-insensitive as in the CLI.
            ("WR/r", 0x13),
            ("LWR/R", 0x1B),
            ("wr/wr", 0x33),
        ],
    )
    def test_access_field(self, field, access):
        assert _meta(f"$.F 00001900 00008023 00000100 {field}").access == access

    @pytest.mark.parametrize("marker", ["Locked", "LOCKED", "L"])
    def test_lock_markers_mean_19(self, marker):
        assert _meta(f"$.F 00001900 00008023 00000100 {marker}").access == 0x19

    def test_an_unreadable_access_field_keeps_the_addresses(self):
        meta = _meta("$.F 00001900 00008023 00000100 QQ")
        assert (meta.load_address, meta.access) == (0x1900, None)


# -- Syntax 2: up to two hex fields and a DFS access marker --


class TestSyntax2:
    @pytest.mark.parametrize("marker", ["Locked", "LOCKED", "L"])
    def test_dfs_marker_after_exec(self, marker):
        # The marker sits where syntax 1 has its length (TubeHost, BeebLink, bbcim).
        meta = _meta(f"$.ELITE FFFF0E00 FFFF8023 {marker}")
        assert (meta.load_address, meta.exec_address, meta.access) == (0xFFFF0E00, 0xFFFF8023, 0x19)

    def test_bbcim_example(self):
        # bbcim's example, with its 6-digit DFS-style addresses.
        meta = _meta("$.ELITE FF0E00 FF8023 Locked CRC=1A2B NEXT ELITEdata")
        assert meta.name == "$.ELITE"
        assert (meta.load_address, meta.exec_address, meta.access) == (0xFFFF0E00, 0xFFFF8023, 0x19)


# -- Syntax 3: a mandatory access field only (directories) --


class TestSyntax3:
    @pytest.mark.parametrize(("field", "access"), [("DLR", 0x09), ("WR", 0x03), ("Locked", 0x19)])
    def test_name_and_access(self, field, access):
        meta = _meta(f"GAMES {field}")
        assert (meta.name, meta.access, meta.load_address) == ("GAMES", access, None)


# -- Load and exec addresses --


class TestAddresses:
    @pytest.mark.parametrize(
        ("field", "address"),
        [
            # Six digits with FF at the top are DFS-style, sign-extended.
            ("FF0E00", 0xFFFF0E00),
            ("ff8023", 0xFFFF8023),
            # Otherwise addresses are taken as written.
            ("7F0E00", 0x007F0E00),
            ("00FF0E00", 0x00FF0E00),
            ("FFFF0E00", 0xFFFF0E00),
        ],
    )
    def test_load_and_exec(self, field, address):
        meta = _meta(f"$.F {field} {field}")
        assert (meta.load_address, meta.exec_address) == (address, address)

    def test_length_is_not_sign_extended(self):
        # Only load and exec addresses are DFS-style addresses.
        assert _meta("$.F 00001900 00008023 FF0000 33").access == 0x33


# -- The name field --


class TestName:
    @pytest.mark.parametrize(
        ("field", "name"),
        [
            ('"MY FILE"', "MY FILE"),
            ('"A%22B"', 'A"B'),
            ('"100%25"', "100%"),
            ('"caf%E9"', "café"),
            ('"%41%42"', "AB"),
            ('"TAPE"', "TAPE"),
            # Unquoted names run to the next space; " and % count as themselves.
            ('A"B', 'A"B'),
            ("50%off", "50%off"),
        ],
    )
    def test_name(self, field, name):
        assert _meta(f"{field} 00001900 00008023").name == name

    def test_tape_prefix_introduces_the_name(self):
        meta = _meta("TAPE HELLO 00001900 00008023")
        assert (meta.name, meta.load_address) == ("HELLO", 0x1900)

    def test_an_unterminated_quoted_name_is_invalid(self):
        assert parse_inf_line('"MY FILE 00001900 00008023') is None

    def test_a_name_alone_is_invalid(self):
        assert parse_inf_line("$.ONLY") is None


# -- Extra info fields and NEXT --


class TestExtraInfo:
    @pytest.mark.parametrize(
        "line",
        [
            "$.F 00001900 00008023 00000100 33 CRC=1234",
            "$.F 00001900 00008023 00000100 33 CRC32=DEADBEEF OPT4=3",
            "$.F 00001900 00008023 00000100 33 CRC= 1234",  # deprecated form
            '$.F 00001900 00008023 00000100 33 DIRTITLE="MY DISC"',
            "$.F 00001900 00008023 00000100 33 KEY=",
            "$.F 00001900 00008023 00000100 33 NEXT $.G",
        ],
    )
    def test_extra_fields_do_not_disturb_the_metadata(self, line):
        meta = _meta(line)
        assert (meta.load_address, meta.exec_address, meta.access) == (0x1900, 0x8023, 0x33)

    def test_extra_fields_after_a_short_line(self):
        meta = _meta("$.F 00001900 00008023 CRC=1234")
        assert (meta.exec_address, meta.access) == (0x8023, 0x33)


# -- Lines and characters --


class TestLines:
    @pytest.mark.parametrize("ending", ["\n", "\r", "\r\n"])
    def test_only_the_first_line_counts(self, ending):
        meta = _meta(f"$.F 00001900 00008023 00000100 19{ending}IGNORED 1 2 3 4")
        assert meta.access == 0x19

    def test_tabs_separate_fields(self):
        assert _meta("$.F\t00001900\t00008023\t00000100\t19").access == 0x19

    def test_read_inf_file_keeps_raw_eight_bit_names(self, tmp_path):
        filepath = tmp_path / "F.inf"
        filepath.write_bytes(b"CAF\xc9 00001900 00008023\r\n")
        _source, meta = read_inf_file(filepath)
        assert meta.name == "CAFÉ"


# -- Writing, per the producer rules --


class TestWriting:
    def test_plain_name_is_unquoted_with_eight_digit_addresses(self):
        line = format_trad_inf_line("$.ELITE", 0xFFFF0E00, 0xFFFF8023, 0x1000, 0x19)
        assert line.split() == ["$.ELITE", "FFFF0E00", "FFFF8023", "00001000", "19"]

    @pytest.mark.parametrize(
        ("name", "field"),
        [
            ("MY FILE", '"MY FILE"'),
            ("TAPE", '"TAPE"'),
            ('"QUOTED', '"%22QUOTED"'),
            ("café", '"caf%E9"'),
            ("", '""'),
        ],
    )
    def test_names_that_need_it_are_quoted_and_encoded(self, name, field):
        line = format_trad_inf_line(name, 0x1900, 0x8023, 0x100, 0x33)
        assert line.startswith(field + " ")

    def test_a_percent_inside_a_quoted_name_is_encoded(self):
        line = format_trad_inf_line("50% OFF", 0x1900, 0x8023, 0x100, 0x33)
        assert line.startswith('"50%25 OFF" ')

    def test_the_line_is_seven_bit_ascii(self):
        line = format_trad_inf_line("café ü", 0x1900, 0x8023, 0x100, 0x33)
        assert all(0x20 <= ord(ch) <= 0x7E for ch in line)

    @pytest.mark.parametrize(
        "name", ["$.ELITE", "MY FILE", "TAPE", '"QUOTED', 'A"B', "50% OFF", "café", "!BOOT"]
    )
    def test_round_trip(self, name):
        line = format_trad_inf_line(name, 0xFFFF1900, 0xFFFF8023, 0x1273, 0x1B)
        meta = _meta(line)
        assert (meta.name, meta.load_address, meta.exec_address, meta.access) == (
            name,
            0xFFFF1900,
            0xFFFF8023,
            0x1B,
        )


# -- PiEconetBridge lines are still told apart --


class TestPiEconetBridgeStillDetected:
    def test_pieb_line(self):
        source, meta = parse_inf_line("0 1900 8023 5 0")
        assert source == "inf-pieb"
        assert meta.access == 0x09  # PiEB perm 5 is R|L

    def test_a_hex_looking_name_with_a_long_length_is_traditional(self):
        source, meta = parse_inf_line("ABC 00001900 00008023 00001000 19")
        assert source == "inf-trad"
        assert meta.name == "ABC"


# -- Names in the original medium's character set (#72) --


class TestNameEncoding:
    """A name is stored in the medium's own bytes, through its name codec.

    The ``acorn`` codec (DFS) maps byte &60 to ``£`` and &7C to ``¦``,
    where Latin-1 has ````` and ``|``.
    """

    def test_default_encodes_from_latin_1(self):
        line = format_trad_inf_line("COST£", 0x1900, 0x8023, 0x100, 0x33)
        assert line.startswith('"COST%A3" ')

    def test_writes_the_medium_byte(self):
        # £ is byte &60 on DFS, a printable character needing no quoting.
        line = format_trad_inf_line("COST£", 0x1900, 0x8023, 0x100, 0x33, encoding="acorn")
        assert line.split()[0] == "COST`"

    def test_quoting_is_judged_on_the_medium_bytes(self):
        line = format_trad_inf_line("A £B", 0x1900, 0x8023, 0x100, 0x33, encoding="acorn")
        assert line.startswith('"A `B" ')

    def test_reads_an_unquoted_name_through_the_codec(self):
        assert parse_inf_line("COST` 1900 8023", encoding="acorn")[1].name == "COST£"

    def test_reads_a_percent_encoded_name_through_the_codec(self):
        assert parse_inf_line('"A %60%7C" 1900 8023', encoding="acorn")[1].name == "A £¦"

    def test_a_name_the_codec_cannot_decode_keeps_its_latin_1_bytes(self):
        # Byte &C9 is not ASCII; keeping it as É lets the destination's
        # name rules report it rather than losing it.
        assert parse_inf_line('"CAF%C9" 1900 8023', encoding="ascii")[1].name == "CAFÉ"
        assert parse_inf_line("CAF\xc9 1900 8023", encoding="ascii")[1].name == "CAFÉ"

    @pytest.mark.parametrize("name", ["COST£", "A ¦B", "$.PLAIN", "50% OFF"])
    def test_round_trip_through_the_codec(self, name):
        line = format_trad_inf_line(name, 0x1900, 0x8023, 0x100, 0x33, encoding="acorn")
        assert parse_inf_line(line, encoding="acorn")[1].name == name

    def test_read_inf_file_takes_the_codec(self, tmp_path):
        filepath = tmp_path / "F.inf"
        filepath.write_bytes(b"$.COST` 00001900 00008023\n")
        _source, meta = read_inf_file(filepath, encoding="acorn")
        assert meta.name == "$.COST£"
