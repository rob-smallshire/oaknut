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

Beyond ``oaknut-exception`` — the base layer, whose categorised errors
the tokeniser and de-tokeniser raise — this module has no runtime
dependencies on any other oaknut package.
"""

from __future__ import annotations

from oaknut.basic.datafile import (
    BbcBasicDataFile,
    BbcBasicDataFileBase,
    BbcBasicDataReader,
    BbcBasicDataWriter,
)
from oaknut.basic.detokeniser import detokenise
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
from oaknut.basic.numbering import (
    DEFAULT_LINE_NUMBER,
    DEFAULT_LINE_STEP,
    number_lines,
)
from oaknut.basic.tokeniser import tokenise

__version__ = "12.7.1"

# Canonical load addresses for BBC BASIC programs on each host.
# Programs saved by *SAVE on a real machine use these by default.
BBC_BASIC_LOAD_ADDRESS = 0x1900
ELECTRON_BASIC_LOAD_ADDRESS = 0x0E00

__all__ = [
    "BBC_BASIC_LOAD_ADDRESS",
    "DEFAULT_LINE_NUMBER",
    "DEFAULT_LINE_STEP",
    "ELECTRON_BASIC_LOAD_ADDRESS",
    "AlreadyNumberedError",
    "BASICError",
    "BbcBasicDataFile",
    "BbcBasicDataFileBase",
    "BbcBasicDataReader",
    "BbcBasicDataWriter",
    "DataFileError",
    "DataFileTypeMismatchError",
    "DetokeniseError",
    "Float5RangeError",
    "IntegerRangeError",
    "InvalidLineLengthError",
    "LineNumberOrderError",
    "LineNumberRangeError",
    "LineTooLongError",
    "MissingLineMarkerError",
    "StringTooLongError",
    "TokeniseError",
    "TruncatedProgramError",
    "TruncatedRecordError",
    "UnknownTagError",
    "UnnumberedLineError",
    "detokenise",
    "number_lines",
    "pack_float5",
    "unpack_float5",
    "tokenise",
]
