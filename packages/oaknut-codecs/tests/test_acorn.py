"""Tests for the Acorn/BBC Micro character codec."""

import oaknut.codecs  # noqa: F401 - registers the "acorn" codec
import pytest
from oaknut.codecs import acorn_to_unicode, unicode_to_acorn


class TestAcornToUnicode:
    """Tests for decoding Acorn bytes to Unicode."""

    def test_standard_ascii(self):
        assert acorn_to_unicode(b"HELLO") == "HELLO"

    def test_pound_sign_bbc_micro(self):
        assert acorn_to_unicode(b"COST\x60100") == "COST£100"

    def test_broken_bar_bbc_micro(self):
        assert acorn_to_unicode(b"A\x7cB") == "A¦B"

    def test_mixed_characters(self):
        assert acorn_to_unicode(b"PRICE:\x60500") == "PRICE:£500"

    def test_empty_bytes(self):
        assert acorn_to_unicode(b"") == ""

    def test_high_bit_characters(self):
        assert len(acorn_to_unicode(bytes([0x80, 0xFF]))) == 2


class TestUnicodeToAcorn:
    """Tests for encoding Unicode to Acorn bytes."""

    def test_standard_ascii(self):
        assert unicode_to_acorn("HELLO") == b"HELLO"

    def test_pound_sign_bbc_micro(self):
        assert unicode_to_acorn("COST£100") == b"COST\x60100"

    def test_broken_bar_bbc_micro(self):
        assert unicode_to_acorn("A¦B") == b"A\x7cB"

    def test_empty_string(self):
        assert unicode_to_acorn("") == b""

    def test_round_trip_bbc_micro(self):
        original = "FILE£NAME"
        assert acorn_to_unicode(unicode_to_acorn(original)) == original

    def test_invalid_character_raises(self):
        with pytest.raises(ValueError, match="cannot be encoded"):
            unicode_to_acorn("HELLO\U0001f4be")  # floppy disk emoji

    def test_high_unicode_raises(self):
        with pytest.raises(ValueError, match="cannot be encoded"):
            unicode_to_acorn("TEST™")  # U+2122


class TestCodecInterface:
    """Tests for the Python codec interface."""

    def test_encode_with_codec(self):
        assert "HELLO".encode("acorn") == b"HELLO"

    def test_decode_with_codec(self):
        assert b"HELLO".decode("acorn") == "HELLO"

    def test_encode_pound_sign(self):
        assert "£100".encode("acorn") == b"\x60100"

    def test_decode_pound_sign(self):
        assert b"\x60100".decode("acorn") == "£100"

    def test_codec_round_trip(self):
        original = "TEST£FILE"
        assert original.encode("acorn").decode("acorn") == original

    def test_codec_name_is_case_insensitive(self):
        assert "£".encode("acorn") == b"\x60"
        assert "£".encode("ACORN") == b"\x60"

    def test_encode_errors_strict(self):
        with pytest.raises(UnicodeEncodeError):
            "TEST™".encode("acorn", errors="strict")

    def test_encode_errors_ignore(self):
        assert "TEST™OK".encode("acorn", errors="ignore") == b"TESTOK"

    def test_encode_errors_replace(self):
        assert "TEST™".encode("acorn", errors="replace") == b"TEST?"

    def test_codec_with_file_like(self):
        import io

        buffer = io.BytesIO()
        writer = io.TextIOWrapper(buffer, encoding="acorn")
        writer.write("£100")
        writer.flush()

        buffer.seek(0)
        reader = io.TextIOWrapper(buffer, encoding="acorn")
        assert reader.read() == "£100"


class TestCodecRegistry:
    """Exercise the bits of codec registry integration beyond str.encode."""

    def test_codecs_lookup_returns_info(self):
        import codecs

        assert codecs.lookup("acorn").name == "acorn"

    def test_incremental_encoder_streams_chunks(self):
        import codecs

        encoder = codecs.getincrementalencoder("acorn")()
        out = encoder.encode("COST") + encoder.encode("£") + encoder.encode("100", final=True)
        assert out == b"COST\x60100"

    def test_incremental_decoder_streams_chunks(self):
        import codecs

        decoder = codecs.getincrementaldecoder("acorn")()
        out = decoder.decode(b"COST") + decoder.decode(b"\x60") + decoder.decode(b"100", final=True)
        assert out == "COST£100"

    def test_incremental_encoder_respects_errors(self):
        import codecs

        encoder = codecs.getincrementalencoder("acorn")(errors="replace")
        assert encoder.encode("AĀB") == b"A?B"

    def test_iterencode_and_iterdecode(self):
        import codecs

        out = b"".join(codecs.iterencode(iter(["COST", "£", "100"]), "acorn"))
        assert out == b"COST\x60100"

        text = "".join(codecs.iterdecode(iter([b"COST", b"\x60", b"100"]), "acorn"))
        assert text == "COST£100"
