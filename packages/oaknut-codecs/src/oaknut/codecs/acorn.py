"""Character encoding for the Acorn/BBC Micro character set.

The BBC Micro and Acorn Electron used a variant of ASCII with a couple
of UK-specific characters. This module implements a Python codec for
that encoding and registers it under the name ``"acorn"``::

    text = "COST£100"
    data = text.encode("acorn")   # b"COST\\x60100"
    back = data.decode("acorn")   # "COST£100"

Importing this module (or its package, :mod:`oaknut.codecs`) registers
the codec as a side effect, after which ``"acorn"`` resolves alongside
the stdlib encodings everywhere in the process.

References:
- https://beebwiki.mdfs.net/ASCII
- https://www.acornelectron.co.uk/ugs/electron/acorn_computers/ug-english/appendix_f_eng.html
- https://tobylobster.github.io/mos/mos/S-s4.html
"""

from __future__ import annotations

import codecs

# BBC Micro (MODEs 0-6) character mappings: Acorn byte values that differ
# from ASCII, mapped to the Unicode characters they stand for.
BBC_MICRO_TO_UNICODE = {
    0x60: "£",  # Backtick replaced with pound sign
    0x7C: "¦",  # Vertical bar replaced with broken bar
}

# Reverse mapping for encoding Unicode to BBC Micro bytes.
UNICODE_TO_BBC_MICRO = {v: k for k, v in BBC_MICRO_TO_UNICODE.items()}


class AcornCodec(codecs.Codec):
    """Codec for the Acorn/BBC Micro character encoding."""

    def encode(self, input: str, errors: str = "strict") -> tuple[bytes, int]:
        """Encode a Unicode string to Acorn bytes.

        Args:
            input: Unicode string to encode.
            errors: Error handling ('strict', 'ignore', 'replace').

        Returns:
            Tuple of (encoded bytes, length of input consumed).
        """
        output = bytearray()
        for i, char in enumerate(input):
            if char in UNICODE_TO_BBC_MICRO:
                output.append(UNICODE_TO_BBC_MICRO[char])
            else:
                code_point = ord(char)
                if code_point > 255:
                    if errors == "strict":
                        raise UnicodeEncodeError(
                            "acorn",
                            input,
                            i,
                            i + 1,
                            f"Character '{char}' (U+{code_point:04X}) cannot be "
                            f"encoded in Acorn character set",
                        )
                    elif errors == "ignore":
                        continue
                    elif errors == "replace":
                        output.append(ord("?"))
                    else:
                        raise ValueError(f"Unknown error handling: {errors}")
                else:
                    output.append(code_point)

        return bytes(output), len(input)

    def decode(self, input: bytes, errors: str = "strict") -> tuple[str, int]:
        """Decode Acorn bytes to a Unicode string.

        Args:
            input: Bytes in Acorn encoding.
            errors: Error handling ('strict', 'ignore', 'replace').

        Returns:
            Tuple of (decoded string, length of input consumed).
        """
        output = []
        for byte in input:
            if byte in BBC_MICRO_TO_UNICODE:
                output.append(BBC_MICRO_TO_UNICODE[byte])
            else:
                # Standard ASCII or high-bit characters.
                output.append(chr(byte))

        return "".join(output), len(input)


# The Acorn codec is byte-for-byte stateless, so a single shared instance
# backs every registry entry point — the incremental encoder and decoder,
# the stream reader/writer, and the non-incremental encode/decode callables.
_SHARED_ACORN_CODEC = AcornCodec()


class AcornIncrementalEncoder(codecs.IncrementalEncoder):
    """Incremental encoder for Acorn encoding."""

    def encode(self, input: str, final: bool = False) -> bytes:
        return _SHARED_ACORN_CODEC.encode(input, self.errors)[0]


class AcornIncrementalDecoder(codecs.IncrementalDecoder):
    """Incremental decoder for Acorn encoding."""

    def decode(self, input: bytes, final: bool = False) -> str:
        return _SHARED_ACORN_CODEC.decode(input, self.errors)[0]


class AcornStreamWriter(AcornCodec, codecs.StreamWriter):
    """Stream writer for Acorn encoding."""


class AcornStreamReader(AcornCodec, codecs.StreamReader):
    """Stream reader for Acorn encoding."""


def getregentry(name: str | None = None) -> codecs.CodecInfo:
    """Return the codec registry entry for the Acorn encoding."""
    return codecs.CodecInfo(
        name="acorn",
        encode=_SHARED_ACORN_CODEC.encode,
        decode=_SHARED_ACORN_CODEC.decode,
        incrementalencoder=AcornIncrementalEncoder,
        incrementaldecoder=AcornIncrementalDecoder,
        streamreader=AcornStreamReader,
        streamwriter=AcornStreamWriter,
    )


def search_function(encoding: str) -> codecs.CodecInfo | None:
    """Codec registry search function recognising the ``"acorn"`` name."""
    if encoding.lower() == "acorn":
        return getregentry(encoding)
    return None


# Register the codec as an import side effect.
codecs.register(search_function)


def acorn_to_unicode(data: bytes) -> str:
    """Decode Acorn-encoded bytes to a Unicode string."""
    return data.decode("acorn")


def unicode_to_acorn(text: str) -> bytes:
    """Encode a Unicode string to Acorn-encoded bytes.

    Raises:
        UnicodeEncodeError: If *text* contains characters that cannot be
            encoded in the Acorn character set.
    """
    return text.encode("acorn")
