"""The BBC BASIC II keyword/token table and flag definitions.

Every value here is specific to **BBC BASIC II** (the BBC Micro's 16 KB
language ROM) and was transcribed from the disassembly's keyword table
at ``&8071``-``&836C``. BASIC IV (Master) keeps the scheme but moves the
addresses; BASIC V (Archimedes) uses a different multi-byte scheme. Treat
the mechanism as portable and these values as version II only.

The ROM table is a flat stream of variable-length entries, each::

    <keyword ASCII, bytes < &80> <token byte, bit 7 set> <flag byte>

Two structural facts drive the tables below:

- The tokeniser ("crunch") scans entries **in ROM order** and takes the
  first one that matches at the cursor, which is why :data:`KEYWORDS`
  preserves that order. The scan stops at ``WIDTH`` (token ``&FE``, the
  table-end sentinel), so the five assignment-form pseudo-variable
  entries that follow it are never matched by the tokeniser.
- Those five trailing entries (``PTR=``/``PAGE=``/``TIME=``/``LOMEM=``/
  ``HIMEM=``, tokens ``&CF``-``&D3``) exist purely so the de-tokeniser can
  render the assignment-form tokens back to text. They are folded into
  :data:`TOKEN_TO_KEYWORD` but excluded from :data:`KEYWORDS`.
"""

from __future__ import annotations

# The line-number reference token. Not a table entry: the tokeniser
# produces ``&8D`` followed by a 3-byte encoded line number, and the
# de-tokeniser special-cases it (see :mod:`oaknut.basic.linenumber`).
LINE_NUMBER_TOKEN = 0x8D

# Program-line storage limits. Each line record begins ``&0D <hi> <lo>
# <length>``; the single length byte counts that 4-byte header plus the
# body, so a line body is at most 251 bytes.
HEADER_LENGTH = 4
MAX_LINE_RECORD_LENGTH = 0xFF
MAX_BODY_LENGTH = MAX_LINE_RECORD_LENGTH - HEADER_LENGTH

# Flag-byte bits, read straight from the crunch's bit-by-bit dispatch.
FLAG_CONDITIONAL = 0x01  # suppress token if followed by a name character
FLAG_MIDDLE = 0x02  # enter middle-of-statement state (and disarm line number)
FLAG_START = 0x04  # enter start-of-statement state (and disarm line number)
FLAG_FN_PROC = 0x08  # skip the following identifier without tokenising it
FLAG_LINE_NUMBER = 0x10  # arm: encode the next decimal literal with &8D
FLAG_STOP_LINE = 0x20  # stop tokenising the rest of the line (REM, DATA)
FLAG_PSEUDO_VAR = 0x40  # at statement start, add &40 to the token

# The amount added to a pseudo-variable's function-form token to obtain
# its assignment-form token when it appears at the start of a statement
# (PTR &8F -> &CF, PAGE &90 -> &D0, ...).
PSEUDO_VAR_ASSIGN_OFFSET = 0x40

# The scannable keyword table, in ROM order. Each entry is
# (keyword, token, flags). Order is significant: it resolves shared
# prefixes and the shortest-unambiguous abbreviation (e.g. INPUT before
# INT, PRINT before PROC). The final entry, WIDTH, is the scan sentinel.
KEYWORDS: tuple[tuple[str, int, int], ...] = (
    ("AND", 0x80, 0x00),
    ("ABS", 0x94, 0x00),
    ("ACS", 0x95, 0x00),
    ("ADVAL", 0x96, 0x00),
    ("ASC", 0x97, 0x00),
    ("ASN", 0x98, 0x00),
    ("ATN", 0x99, 0x00),
    ("AUTO", 0xC6, 0x10),
    ("BGET", 0x9A, 0x01),
    ("BPUT", 0xD5, 0x03),
    ("COLOUR", 0xFB, 0x02),
    ("CALL", 0xD6, 0x02),
    ("CHAIN", 0xD7, 0x02),
    ("CHR$", 0xBD, 0x00),
    ("CLEAR", 0xD8, 0x01),
    ("CLOSE", 0xD9, 0x03),
    ("CLG", 0xDA, 0x01),
    ("CLS", 0xDB, 0x01),
    ("COS", 0x9B, 0x00),
    ("COUNT", 0x9C, 0x01),
    ("DATA", 0xDC, 0x20),
    ("DEG", 0x9D, 0x00),
    ("DEF", 0xDD, 0x00),
    ("DELETE", 0xC7, 0x10),
    ("DIV", 0x81, 0x00),
    ("DIM", 0xDE, 0x02),
    ("DRAW", 0xDF, 0x02),
    ("ENDPROC", 0xE1, 0x01),
    ("END", 0xE0, 0x01),
    ("ENVELOPE", 0xE2, 0x02),
    ("ELSE", 0x8B, 0x14),
    ("EVAL", 0xA0, 0x00),
    ("ERL", 0x9E, 0x01),
    ("ERROR", 0x85, 0x04),
    ("EOF", 0xC5, 0x01),
    ("EOR", 0x82, 0x00),
    ("ERR", 0x9F, 0x01),
    ("EXP", 0xA1, 0x00),
    ("EXT", 0xA2, 0x01),
    ("FOR", 0xE3, 0x02),
    ("FALSE", 0xA3, 0x01),
    ("FN", 0xA4, 0x08),
    ("GOTO", 0xE5, 0x12),
    ("GET$", 0xBE, 0x00),
    ("GET", 0xA5, 0x00),
    ("GOSUB", 0xE4, 0x12),
    ("GCOL", 0xE6, 0x02),
    ("HIMEM", 0x93, 0x43),
    ("INPUT", 0xE8, 0x02),
    ("IF", 0xE7, 0x02),
    ("INKEY$", 0xBF, 0x00),
    ("INKEY", 0xA6, 0x00),
    ("INT", 0xA8, 0x00),
    ("INSTR(", 0xA7, 0x00),
    ("LIST", 0xC9, 0x10),
    ("LINE", 0x86, 0x00),
    ("LOAD", 0xC8, 0x02),
    ("LOMEM", 0x92, 0x43),
    ("LOCAL", 0xEA, 0x02),
    ("LEFT$(", 0xC0, 0x00),
    ("LEN", 0xA9, 0x00),
    ("LET", 0xE9, 0x04),
    ("LOG", 0xAB, 0x00),
    ("LN", 0xAA, 0x00),
    ("MID$(", 0xC1, 0x00),
    ("MODE", 0xEB, 0x02),
    ("MOD", 0x83, 0x00),
    ("MOVE", 0xEC, 0x02),
    ("NEXT", 0xED, 0x02),
    ("NEW", 0xCA, 0x01),
    ("NOT", 0xAC, 0x00),
    ("OLD", 0xCB, 0x01),
    ("ON", 0xEE, 0x02),
    ("OFF", 0x87, 0x00),
    ("OR", 0x84, 0x00),
    ("OPENIN", 0x8E, 0x00),
    ("OPENOUT", 0xAE, 0x00),
    ("OPENUP", 0xAD, 0x00),
    ("OSCLI", 0xFF, 0x02),
    ("PRINT", 0xF1, 0x02),
    ("PAGE", 0x90, 0x43),
    ("PTR", 0x8F, 0x43),
    ("PI", 0xAF, 0x01),
    ("PLOT", 0xF0, 0x02),
    ("POINT(", 0xB0, 0x00),
    ("PROC", 0xF2, 0x0A),
    ("POS", 0xB1, 0x01),
    ("RETURN", 0xF8, 0x01),
    ("REPEAT", 0xF5, 0x00),
    ("REPORT", 0xF6, 0x01),
    ("READ", 0xF3, 0x02),
    ("REM", 0xF4, 0x20),
    ("RUN", 0xF9, 0x01),
    ("RAD", 0xB2, 0x00),
    ("RESTORE", 0xF7, 0x12),
    ("RIGHT$(", 0xC2, 0x00),
    ("RND", 0xB3, 0x01),
    ("RENUMBER", 0xCC, 0x10),
    ("STEP", 0x88, 0x00),
    ("SAVE", 0xCD, 0x02),
    ("SGN", 0xB4, 0x00),
    ("SIN", 0xB5, 0x00),
    ("SQR", 0xB6, 0x00),
    ("SPC", 0x89, 0x00),
    ("STR$", 0xC3, 0x00),
    ("STRING$(", 0xC4, 0x00),
    ("SOUND", 0xD4, 0x02),
    ("STOP", 0xFA, 0x01),
    ("TAN", 0xB7, 0x00),
    ("THEN", 0x8C, 0x14),
    ("TO", 0xB8, 0x00),
    ("TAB(", 0x8A, 0x00),
    ("TRACE", 0xFC, 0x12),
    ("TIME", 0x91, 0x43),
    ("TRUE", 0xB9, 0x01),
    ("UNTIL", 0xFD, 0x02),
    ("USR", 0xBA, 0x00),
    ("VDU", 0xEF, 0x02),
    ("VAL", 0xBB, 0x00),
    ("VPOS", 0xBC, 0x01),
    ("WIDTH", 0xFE, 0x02),
)

# The five assignment-form pseudo-variable entries that follow WIDTH in
# ROM. The tokeniser never reaches them (it produces these tokens
# arithmetically, via FLAG_PSEUDO_VAR); they exist only so the
# de-tokeniser can render &CF-&D3 back to text.
_ASSIGNMENT_FORMS: tuple[tuple[str, int], ...] = (
    ("PAGE", 0xD0),
    ("PTR", 0xCF),
    ("TIME", 0xD1),
    ("LOMEM", 0xD2),
    ("HIMEM", 0xD3),
)

# token byte -> keyword spelling, covering every entry in the ROM table.
# &8D (line number) and &CE (unused gap) are deliberately absent.
TOKEN_TO_KEYWORD: dict[int, str] = {token: keyword for keyword, token, _flags in KEYWORDS}
TOKEN_TO_KEYWORD.update({token: keyword for keyword, token in _ASSIGNMENT_FORMS})
