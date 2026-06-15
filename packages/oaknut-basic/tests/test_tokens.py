"""Structural checks on the transcribed BBC BASIC II keyword table.

These guard the hand-transcribed table against drift: counts, token
uniqueness, and a few spot-checks of the version-sensitive and
flag-bearing entries called out in the disassembly notes.
"""

from oaknut.basic import tokens


class TestTableShape:
    def test_scannable_entry_count(self):
        # 126 ROM entries minus the 5 assignment-form trailers = 121.
        assert len(tokens.KEYWORDS) == 121

    def test_token_to_keyword_covers_every_rom_entry(self):
        assert len(tokens.TOKEN_TO_KEYWORD) == 126

    def test_scannable_tokens_are_unique(self):
        scan_tokens = [token for _kw, token, _flags in tokens.KEYWORDS]
        assert len(scan_tokens) == len(set(scan_tokens))

    def test_every_token_has_bit_7_set(self):
        assert all(token & 0x80 for token in tokens.TOKEN_TO_KEYWORD)

    def test_line_number_and_gap_tokens_are_absent(self):
        assert 0x8D not in tokens.TOKEN_TO_KEYWORD  # line-number token
        assert 0xCE not in tokens.TOKEN_TO_KEYWORD  # unused gap

    def test_width_is_the_final_scan_entry(self):
        assert tokens.KEYWORDS[-1] == ("WIDTH", 0xFE, 0x02)


class TestSpotChecks:
    def test_common_keywords(self):
        by_keyword = {kw: token for kw, token, _flags in tokens.KEYWORDS}
        assert by_keyword["PRINT"] == 0xF1
        assert by_keyword["AND"] == 0x80
        assert by_keyword["GOTO"] == 0xE5
        assert by_keyword["REM"] == 0xF4

    def test_version_sensitive_function_forms(self):
        by_keyword = {kw: token for kw, token, _flags in tokens.KEYWORDS}
        assert by_keyword["OPENIN"] == 0x8E
        assert by_keyword["OPENOUT"] == 0xAE
        assert by_keyword["OPENUP"] == 0xAD
        assert by_keyword["PTR"] == 0x8F

    def test_pseudo_variable_assignment_forms_detokenise(self):
        # &CF-&D3 are the assignment forms, used only by the de-tokeniser.
        assert tokens.TOKEN_TO_KEYWORD[0xCF] == "PTR"
        assert tokens.TOKEN_TO_KEYWORD[0xD0] == "PAGE"
        assert tokens.TOKEN_TO_KEYWORD[0xD3] == "HIMEM"

    def test_ordering_resolves_shared_prefixes(self):
        order = [kw for kw, _token, _flags in tokens.KEYWORDS]
        assert order.index("INPUT") < order.index("INT")
        assert order.index("PRINT") < order.index("PROC")

    def test_flag_bits_on_known_entries(self):
        by_keyword = {kw: flags for kw, _token, flags in tokens.KEYWORDS}
        assert by_keyword["REM"] & tokens.FLAG_STOP_LINE
        assert by_keyword["DATA"] & tokens.FLAG_STOP_LINE
        assert by_keyword["GOTO"] & tokens.FLAG_LINE_NUMBER
        assert by_keyword["THEN"] & tokens.FLAG_LINE_NUMBER
        assert by_keyword["THEN"] & tokens.FLAG_START
        assert by_keyword["FN"] & tokens.FLAG_FN_PROC
        assert by_keyword["PROC"] & tokens.FLAG_FN_PROC
        assert by_keyword["PAGE"] & tokens.FLAG_PSEUDO_VAR
        assert by_keyword["END"] & tokens.FLAG_CONDITIONAL
