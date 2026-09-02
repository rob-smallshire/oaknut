"""BBC BASIC tokenisation and detokenisation.

Tokenised BBC BASIC is a compact on-disc representation in which
keywords like ``PRINT`` and ``GOTO`` are replaced with single bytes,
line numbers are packed at the start of each line, and string
literals and ``REM`` comments are stored in the Acorn character
encoding. This module converts between source text and that byte
representation.

BBC BASIC is a language, not a text encoding — tokenised programs
are bytecode, not text. The two functions here therefore work in
``str`` ↔ ``bytes`` pairs and must never be composed with
``DFSPath.read_text`` / ``write_text`` (which would silently mangle
the bytecode). The canonical way to move a BASIC program through a
disc image is ``DFSPath.read_basic`` / ``write_basic``, which wrap
these functions with the correct load-address default.

The tokeniser and de-tokeniser raise categorised errors from
``oaknut-exception``; the data-file API additionally uses the ``acorn``
text codec from ``oaknut-codecs`` for string records. Both are bottom-layer
packages, so ``oaknut-basic`` stays independent of the file and disc-image
layers.
"""

from __future__ import annotations

from oaknut.basic.datafile import (
    BbcBasicDataFile,
    BbcBasicDataFileBase,
    BbcBasicDataReader,
    BbcBasicDataWriter,
)
from oaknut.basic.detect import Detection, Verdict, detect
from oaknut.basic.detokeniser import detokenise, detokenise_body
from oaknut.basic.dialect import BASIC_II, BASIC_V, Dialect
from oaknut.basic.exceptions import (
    AlreadyNumberedError,
    BASICError,
    DataFileError,
    DataFileTypeMismatchError,
    DetokeniseError,
    Float5RangeError,
    IntegerRangeError,
    InvalidLineLengthError,
    LineNumberOrderError,
    LineNumberRangeError,
    LineTooLongError,
    MissingLineMarkerError,
    StringTooLongError,
    TokeniseError,
    TruncatedProgramError,
    TruncatedRecordError,
    UnknownTagError,
    UnnumberedLineError,
)
from oaknut.basic.float5 import pack_float5, unpack_float5
from oaknut.basic.linenumber import decode_line_number
from oaknut.basic.numbering import (
    DEFAULT_LINE_NUMBER,
    DEFAULT_LINE_STEP,
    number_lines,
)
from oaknut.basic.scanner import (
    LineRecord,
    Token,
    TokenKind,
    scan,
    scan_program,
)
from oaknut.basic.tokeniser import Crunch, tokenise
from oaknut.basic.tokens import (
    FLAG_CONDITIONAL,
    FLAG_FN_PROC,
    FLAG_LINE_NUMBER,
    FLAG_MIDDLE,
    FLAG_PSEUDO_VAR,
    FLAG_START,
    FLAG_STOP_LINE,
    KEYWORDS,
    LINE_NUMBER_TOKEN,
    TOKEN_TO_KEYWORD,
)

__version__ = "12.16.0"

# Canonical load addresses for BBC BASIC programs on each host.
# Programs saved by *SAVE on a real machine use these by default.
BBC_BASIC_LOAD_ADDRESS = 0x1900
ELECTRON_BASIC_LOAD_ADDRESS = 0x0E00

__all__ = [
    "BASIC_II",
    "BASIC_V",
    "BBC_BASIC_LOAD_ADDRESS",
    "DEFAULT_LINE_NUMBER",
    "DEFAULT_LINE_STEP",
    "ELECTRON_BASIC_LOAD_ADDRESS",
    "FLAG_CONDITIONAL",
    "FLAG_FN_PROC",
    "FLAG_LINE_NUMBER",
    "FLAG_MIDDLE",
    "FLAG_PSEUDO_VAR",
    "FLAG_START",
    "FLAG_STOP_LINE",
    "KEYWORDS",
    "LINE_NUMBER_TOKEN",
    "TOKEN_TO_KEYWORD",
    "AlreadyNumberedError",
    "BASICError",
    "BbcBasicDataFile",
    "BbcBasicDataFileBase",
    "BbcBasicDataReader",
    "BbcBasicDataWriter",
    "Crunch",
    "DataFileError",
    "DataFileTypeMismatchError",
    "Detection",
    "DetokeniseError",
    "Dialect",
    "Float5RangeError",
    "IntegerRangeError",
    "InvalidLineLengthError",
    "LineNumberOrderError",
    "LineNumberRangeError",
    "LineRecord",
    "LineTooLongError",
    "MissingLineMarkerError",
    "StringTooLongError",
    "Token",
    "TokenKind",
    "TokeniseError",
    "TruncatedProgramError",
    "TruncatedRecordError",
    "UnknownTagError",
    "UnnumberedLineError",
    "Verdict",
    "decode_line_number",
    "detect",
    "detokenise",
    "detokenise_body",
    "number_lines",
    "pack_float5",
    "scan",
    "scan_program",
    "unpack_float5",
    "tokenise",
]
