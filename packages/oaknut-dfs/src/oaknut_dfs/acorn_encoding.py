"""Character encoding for Acorn/BBC Micro character set.

The BBC Micro and Acorn Electron used a variant of ASCII with some UK-specific
characters. This module implements a Python codec for Acorn encoding.

Usage:
    # Encoding
    text = "COST£100"
    data = text.encode('acorn')

    # Decoding
    data = b"COST\x60100"
    text = data.decode('acorn')

References:
- https://beebwiki.mdfs.net/ASCII
- https://www.acornelectron.co.uk/ugs/electron/acorn_computers/ug-english/appendix_f_eng.html
- https://tobylobster.github.io/mos/mos/S-s4.html
"""

import codecs
from typing import Tuple


# BBC Micro (MODEs 0-6) character mappings
# Maps Acorn byte values to Unicode characters where they differ from ASCII
BBC_MICRO_TO_UNICODE = {
    0x60: '£',  # Backtick replaced with pound sign
    0x7C: '¦',  # Vertical bar replaced with broken bar
}

# Reverse mapping for encoding Unicode to BBC Micro
UNICODE_TO_BBC_MICRO = {v: k for k, v in BBC_MICRO_TO_UNICODE.items()}


class AcornCodec(codecs.Codec):
    """Codec for Acorn/BBC Micro character encoding."""

    def encode(self, input: str, errors: str = 'strict') -> Tuple[bytes, int]:
        """
        Encode Unicode string to Acorn bytes.

        Args:
            input: Unicode string to encode
            errors: Error handling ('strict', 'ignore', 'replace')

        Returns:
            Tuple of (encoded bytes, length of input consumed)
        """
        output = bytearray()
        for i, char in enumerate(input):
            if char in UNICODE_TO_BBC_MICRO:
                output.append(UNICODE_TO_BBC_MICRO[char])
            else:
                code_point = ord(char)
                if code_point > 255:
                    if errors == 'strict':
                        raise UnicodeEncodeError(
                            'acorn',
                            input,
                            i,
                            i + 1,
                            f"Character '{char}' (U+{code_point:04X}) cannot be "
                            f"encoded in Acorn character set",
                        )
                    elif errors == 'ignore':
                        continue
                    elif errors == 'replace':
                        output.append(ord('?'))
                    else:
                        raise ValueError(f"Unknown error handling: {errors}")
                else:
                    output.append(code_point)

        return bytes(output), len(input)

    def decode(self, input: bytes, errors: str = 'strict') -> Tuple[str, int]:
        """
        Decode Acorn bytes to Unicode string.

        Args:
            input: Bytes in Acorn encoding
            errors: Error handling ('strict', 'ignore', 'replace')

        Returns:
            Tuple of (decoded string, length of input consumed)
        """
        output = []
        for byte in input:
            if byte in BBC_MICRO_TO_UNICODE:
                output.append(BBC_MICRO_TO_UNICODE[byte])
            else:
                # Standard ASCII or high-bit characters
                output.append(chr(byte))

        return ''.join(output), len(input)


class AcornIncrementalEncoder(codecs.IncrementalEncoder):
    """Incremental encoder for Acorn encoding."""

    def encode(self, input: str, final: bool = False) -> bytes:
        """Encode incrementally."""
        return AcornCodec().encode(input, self.errors)[0]


class AcornIncrementalDecoder(codecs.IncrementalDecoder):
    """Incremental decoder for Acorn encoding."""

    def decode(self, input: bytes, final: bool = False) -> str:
        """Decode incrementally."""
        return AcornCodec().decode(input, self.errors)[0]


class AcornStreamWriter(AcornCodec, codecs.StreamWriter):
    """Stream writer for Acorn encoding."""

    pass


class AcornStreamReader(AcornCodec, codecs.StreamReader):
    """Stream reader for Acorn encoding."""

    pass


def getregentry(name: str = None) -> codecs.CodecInfo:
    """Get codec registry entry."""
    return codecs.CodecInfo(
        name='acorn',
        encode=AcornCodec().encode,
        decode=AcornCodec().decode,
        incrementalencoder=AcornIncrementalEncoder,
        incrementaldecoder=AcornIncrementalDecoder,
        streamreader=AcornStreamReader,
        streamwriter=AcornStreamWriter,
    )


def search_function(encoding: str) -> codecs.CodecInfo | None:
    """Search function for codec registry."""
    if encoding.lower() in ('acorn', 'acorn-bbc', 'bbc-micro'):
        return getregentry(encoding)
    return None


# Register the codec
codecs.register(search_function)


# Convenience functions for backward compatibility
def acorn_to_unicode(data: bytes) -> str:
    """
    Decode Acorn-encoded bytes to Unicode string.

    Args:
        data: Raw bytes in Acorn encoding

    Returns:
        Decoded Unicode string
    """
    return data.decode('acorn')


def unicode_to_acorn(text: str) -> bytes:
    """
    Encode Unicode string to Acorn encoding.

    Args:
        text: Unicode string to encode

    Returns:
        Encoded bytes in Acorn format

    Raises:
        UnicodeEncodeError: If text contains characters that cannot be encoded
    """
    return text.encode('acorn')


def is_valid_acorn_filename_char(char: str) -> bool:
    """
    Check if a character is valid in an Acorn DFS filename.

    Args:
        char: Single character to check

    Returns:
        True if character is valid in filenames

    Notes:
        Per "Guide to Disc Formats.pdf", forbidden characters are:
        - '#', '*', ':', '.', '!' (except '!' as first character)
        - Top-bit set characters (>127)
        - Control characters (<32)

        This function checks general validity. Position-specific rules
        (like '!' only at position 0) must be checked separately.
    """
    # Standard alphanumeric
    if 'A' <= char <= 'Z' or '0' <= char <= '9':
        return True

    # Allowed punctuation (excluding forbidden: # * : . !)
    if char in '$%&()+@^_-':
        return True

    # UK-specific characters
    if char == '£':
        return True

    return False


def sanitize_for_acorn(text: str) -> str:
    """
    Sanitize a Unicode string for use as Acorn DFS filename.

    Args:
        text: String to sanitize

    Returns:
        Sanitized string with invalid characters removed or replaced

    Notes:
        - Converts lowercase to uppercase
        - Removes characters that can't be encoded
    """
    # Convert to uppercase
    text = text.upper()

    # Keep only valid characters
    sanitized = ''.join(c for c in text if is_valid_acorn_filename_char(c))

    return sanitized
