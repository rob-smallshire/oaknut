"""Tests for Acorn character encoding."""

import pytest
import oaknut_dfs.acorn_encoding  # Register codec
from oaknut_dfs.acorn_encoding import (
    acorn_to_unicode,
    unicode_to_acorn,
    is_valid_acorn_filename_char,
    sanitize_for_acorn,
)


class TestAcornToUnicode:
    """Tests for decoding Acorn bytes to Unicode."""

    def test_standard_ascii(self):
        """Standard ASCII characters decode normally."""
        data = b"HELLO"
        assert acorn_to_unicode(data) == "HELLO"

    def test_pound_sign_bbc_micro(self):
        """Pound sign at 0x60 on BBC Micro."""
        data = b"COST\x60100"  # "COST£100"
        result = acorn_to_unicode(data)
        assert result == "COST£100"

    def test_broken_bar_bbc_micro(self):
        """Broken bar at 0x7C on BBC Micro."""
        data = b"A\x7CB"  # "A¦B"
        result = acorn_to_unicode(data)
        assert result == "A¦B"

    def test_mixed_characters(self):
        """Mixed standard and UK characters."""
        data = b"PRICE:\x60500"  # "PRICE:£500"
        result = acorn_to_unicode(data)
        assert result == "PRICE:£500"

    def test_empty_bytes(self):
        """Empty bytes decode to empty string."""
        assert acorn_to_unicode(b"") == ""

    def test_alphanumeric(self):
        """Alphanumeric characters decode normally."""
        data = b"TEST123"
        assert acorn_to_unicode(data) == "TEST123"

    def test_spaces(self):
        """Spaces decode normally."""
        data = b"HELLO WORLD"
        assert acorn_to_unicode(data) == "HELLO WORLD"

    def test_high_bit_characters(self):
        """High-bit characters (128-255) pass through."""
        data = bytes([0x80, 0xFF])
        result = acorn_to_unicode(data)
        assert len(result) == 2


class TestUnicodeToAcorn:
    """Tests for encoding Unicode to Acorn bytes."""

    def test_standard_ascii(self):
        """Standard ASCII characters encode normally."""
        text = "HELLO"
        assert unicode_to_acorn(text) == b"HELLO"

    def test_pound_sign_bbc_micro(self):
        """Pound sign encodes to 0x60 on BBC Micro."""
        text = "COST£100"
        result = unicode_to_acorn(text)
        assert result == b"COST\x60100"

    def test_broken_bar_bbc_micro(self):
        """Broken bar encodes to 0x7C on BBC Micro."""
        text = "A¦B"
        result = unicode_to_acorn(text)
        assert result == b"A\x7CB"

    def test_mixed_characters(self):
        """Mixed standard and UK characters."""
        text = "PRICE:£500"
        result = unicode_to_acorn(text)
        assert result == b"PRICE:\x60500"

    def test_empty_string(self):
        """Empty string encodes to empty bytes."""
        assert unicode_to_acorn("") == b""

    def test_alphanumeric(self):
        """Alphanumeric characters encode normally."""
        text = "TEST123"
        assert unicode_to_acorn(text) == b"TEST123"

    def test_round_trip_bbc_micro(self):
        """Round trip encoding/decoding preserves data."""
        original = "FILE£NAME"
        encoded = unicode_to_acorn(original)
        decoded = acorn_to_unicode(encoded)
        assert decoded == original

    def test_round_trip_standard_ascii(self):
        """Round trip with standard ASCII."""
        original = "TESTFILE"
        encoded = unicode_to_acorn(original)
        decoded = acorn_to_unicode(encoded)
        assert decoded == original

    def test_invalid_character_raises(self):
        """Characters outside 0-255 range raise ValueError."""
        text = "HELLO\U0001F4BE"  # Contains floppy disk emoji
        with pytest.raises(ValueError, match="cannot be encoded"):
            unicode_to_acorn(text)

    def test_high_unicode_raises(self):
        """High Unicode characters raise ValueError."""
        text = "TEST™"  # Trademark symbol (U+2122)
        with pytest.raises(ValueError, match="cannot be encoded"):
            unicode_to_acorn(text)


class TestIsValidAcornFilenameChar:
    """Tests for filename character validation."""

    def test_uppercase_letters(self):
        """Uppercase letters are valid."""
        for char in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            assert is_valid_acorn_filename_char(char)

    def test_digits(self):
        """Digits are valid."""
        for char in "0123456789":
            assert is_valid_acorn_filename_char(char)

    def test_pound_sign(self):
        """Pound sign is valid."""
        assert is_valid_acorn_filename_char('£')

    def test_common_punctuation(self):
        """Common punctuation is valid."""
        for char in "!#$%&()+-.@^_":
            assert is_valid_acorn_filename_char(char)

    def test_lowercase_invalid(self):
        """Lowercase letters are invalid (should be uppercase)."""
        assert not is_valid_acorn_filename_char('a')
        assert not is_valid_acorn_filename_char('z')

    def test_space_invalid(self):
        """Spaces are typically invalid in filenames."""
        assert not is_valid_acorn_filename_char(' ')

    def test_special_chars_invalid(self):
        """Special characters not in allowed set are invalid."""
        assert not is_valid_acorn_filename_char('*')
        assert not is_valid_acorn_filename_char('/')
        assert not is_valid_acorn_filename_char('\\')
        assert not is_valid_acorn_filename_char(':')


class TestSanitizeForAcorn:
    """Tests for filename sanitization."""

    def test_converts_to_uppercase(self):
        """Lowercase converts to uppercase."""
        assert sanitize_for_acorn("hello") == "HELLO"

    def test_removes_invalid_chars(self):
        """Invalid characters are removed."""
        assert sanitize_for_acorn("HE*LLO") == "HELLO"

    def test_preserves_valid_chars(self):
        """Valid characters are preserved."""
        assert sanitize_for_acorn("TEST-123") == "TEST-123"

    def test_handles_pound_sign(self):
        """Pound sign is preserved."""
        assert sanitize_for_acorn("£100") == "£100"

    def test_removes_spaces(self):
        """Spaces are removed."""
        assert sanitize_for_acorn("HELLO WORLD") == "HELLOWORLD"

    def test_mixed_case_and_invalid(self):
        """Mixed case and invalid characters."""
        assert sanitize_for_acorn("TeSt*FiLe.BIN") == "TESTFILE.BIN"

    def test_empty_string(self):
        """Empty string remains empty."""
        assert sanitize_for_acorn("") == ""

    def test_all_invalid_chars(self):
        """String with all invalid characters becomes empty."""
        assert sanitize_for_acorn("***") == ""

    def test_preserves_numbers(self):
        """Numbers are preserved."""
        assert sanitize_for_acorn("file123") == "FILE123"

    def test_preserves_punctuation(self):
        """Allowed punctuation is preserved."""
        assert sanitize_for_acorn("test!@#$%") == "TEST!@#$%"


class TestEncodingIntegration:
    """Integration tests for encoding with DFS filenames."""

    def test_typical_filename(self):
        """Typical DFS filename encodes/decodes correctly."""
        filename = "ELITE"
        encoded = unicode_to_acorn(filename)
        assert encoded == b"ELITE"
        assert acorn_to_unicode(encoded) == filename

    def test_filename_with_number(self):
        """Filename with number."""
        filename = "LEVEL1"
        encoded = unicode_to_acorn(filename)
        assert encoded == b"LEVEL1"
        assert acorn_to_unicode(encoded) == filename

    def test_filename_with_pound(self):
        """Filename containing pound sign."""
        filename = "£MONEY"
        encoded = unicode_to_acorn(filename)
        assert b'\x60' in encoded  # Contains pound at 0x60
        assert acorn_to_unicode(encoded) == filename

    def test_max_length_filename(self):
        """Maximum 7-character filename."""
        filename = "ABCDEFG"
        encoded = unicode_to_acorn(filename)
        assert len(encoded) == 7
        assert acorn_to_unicode(encoded) == filename

    def test_disk_title(self):
        """Disk title (12 characters)."""
        title = "MY DISK 2024"
        encoded = unicode_to_acorn(title)
        assert acorn_to_unicode(encoded) == title

    def test_disk_title_with_pound(self):
        """Disk title with pound sign."""
        title = "COST: £50"
        encoded = unicode_to_acorn(title)
        decoded = acorn_to_unicode(encoded)
        assert decoded == title
        assert b'\x60' in encoded


class TestCodecInterface:
    """Tests for Python codec interface."""

    def test_encode_with_codec(self):
        """Encode using Python's standard .encode() method."""
        text = "HELLO"
        encoded = text.encode('acorn')
        assert encoded == b"HELLO"

    def test_decode_with_codec(self):
        """Decode using Python's standard .decode() method."""
        data = b"HELLO"
        decoded = data.decode('acorn')
        assert decoded == "HELLO"

    def test_encode_pound_sign(self):
        """Encode pound sign using codec."""
        text = "£100"
        encoded = text.encode('acorn')
        assert encoded == b"\x60100"

    def test_decode_pound_sign(self):
        """Decode pound sign using codec."""
        data = b"\x60100"
        decoded = data.decode('acorn')
        assert decoded == "£100"

    def test_encode_broken_bar(self):
        """Encode broken bar using codec."""
        text = "A¦B"
        encoded = text.encode('acorn')
        assert encoded == b"A\x7CB"

    def test_decode_broken_bar(self):
        """Decode broken bar using codec."""
        data = b"A\x7CB"
        decoded = data.decode('acorn')
        assert decoded == "A¦B"

    def test_codec_round_trip(self):
        """Round trip through codec."""
        original = "TEST£FILE"
        encoded = original.encode('acorn')
        decoded = encoded.decode('acorn')
        assert decoded == original

    def test_codec_name(self):
        """Test codec is registered as 'acorn'."""
        text = "£"
        assert text.encode('acorn') == b"\x60"
        # Codec is registered as 'acorn'
        assert text.encode('ACORN') == b"\x60"  # Case insensitive

    def test_encode_errors_strict(self):
        """Encoding with strict error handling raises on invalid chars."""
        text = "TEST™"  # Contains trademark symbol
        with pytest.raises(UnicodeEncodeError):
            text.encode('acorn', errors='strict')

    def test_encode_errors_ignore(self):
        """Encoding with ignore error handling skips invalid chars."""
        text = "TEST™OK"
        encoded = text.encode('acorn', errors='ignore')
        assert encoded == b"TESTOK"

    def test_encode_errors_replace(self):
        """Encoding with replace error handling uses ? for invalid chars."""
        text = "TEST™"
        encoded = text.encode('acorn', errors='replace')
        assert encoded == b"TEST?"

    def test_codec_with_file_like(self):
        """Test codec works with file-like operations."""
        import io

        # Write with codec
        buffer = io.BytesIO()
        writer = io.TextIOWrapper(buffer, encoding='acorn')
        writer.write("£100")
        writer.flush()

        # Read with codec
        buffer.seek(0)
        reader = io.TextIOWrapper(buffer, encoding='acorn')
        result = reader.read()
        assert result == "£100"
