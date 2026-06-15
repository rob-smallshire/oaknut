"""Exhaustive, parameterised coverage of the keyword table.

Three sweeps over every entry in the BBC BASIC II keyword table:

- every keyword tokenises to its table token;
- every token de-tokenises to its keyword;
- every keyword's shortest unambiguous ``.`` abbreviation tokenises to
  the same token.

Spot-checks in ``test_tokens.py`` guard the transcription; these guard
the *codec's* behaviour across the whole table at once.
"""

import pytest
from oaknut.basic import detokenise, tokenise
from oaknut.basic.tokens import FLAG_PSEUDO_VAR, KEYWORDS, TOKEN_TO_KEYWORD


def _body(statement: str) -> bytes:
    program = tokenise("10" + statement)
    return program[4 : program[3]]


def _ids(entries):
    return [kw for kw, _t, _f in entries]


# ---------------------------------------------------------------------------
# Minimal abbreviations
# ---------------------------------------------------------------------------


def _minimal_abbreviation(keyword: str) -> str | None:
    """Shortest ``prefix.`` that resolves to *keyword* in ROM scan order.

    Mirrors the crunch: the first table entry whose leading characters
    match the typed prefix wins, so a keyword shadowed at every prefix by
    an earlier entry (``END`` behind ``ENDPROC``) has no abbreviation.
    """
    for length in range(1, len(keyword)):
        prefix = keyword[:length]
        first = next(kw for kw, _t, _f in KEYWORDS if kw[:length] == prefix)
        if first == keyword:
            return prefix + "."
    return None


_ABBREVIATED = [
    (kw, token, abbrev)
    for kw, token, flags in KEYWORDS
    if (abbrev := _minimal_abbreviation(kw)) is not None
]


# ---------------------------------------------------------------------------
# Sweeps
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("keyword", "token", "flags"), KEYWORDS, ids=_ids(KEYWORDS))
def test_every_keyword_tokenises_to_its_token(keyword, token, flags):
    # Pseudo-variables tokenise to their function-form (table) token only
    # in a value position; at the start of a statement they take the
    # assignment form. Put them after ``A=`` so the table token is emitted.
    prefix = " A=" if flags & FLAG_PSEUDO_VAR else " "
    assert _body(prefix + keyword) == prefix.encode("latin-1") + bytes([token])


@pytest.mark.parametrize(("keyword", "token"), [(kw, t) for kw, t, _f in KEYWORDS], ids=_ids(KEYWORDS))
def test_every_token_detokenises_to_its_keyword(keyword, token):
    program = b"\x0d\x00\x0a\x05" + bytes([token]) + b"\x0d\xff"
    assert detokenise(program) == f"10{keyword}\n"


def test_assignment_form_tokens_detokenise():
    # The five &CF-&D3 entries exist only for the de-tokeniser.
    for token in (0xCF, 0xD0, 0xD1, 0xD2, 0xD3):
        program = b"\x0d\x00\x0a\x05" + bytes([token]) + b"\x0d\xff"
        assert detokenise(program) == f"10{TOKEN_TO_KEYWORD[token]}\n"


@pytest.mark.parametrize(
    ("keyword", "token", "abbrev"),
    _ABBREVIATED,
    ids=[kw for kw, _t, _a in _ABBREVIATED],
)
def test_minimal_abbreviation_tokenises_to_the_keyword(keyword, token, abbrev):
    flags = next(f for kw, _t, f in KEYWORDS if kw == keyword)
    prefix = " A=" if flags & FLAG_PSEUDO_VAR else " "
    assert _body(prefix + abbrev) == prefix.encode("latin-1") + bytes([token])


def test_abbreviation_examples_from_the_disassembly():
    # The curated table order is what makes these resolve (see the
    # disassembly notes): P. -> PRINT, PR. -> PRINT, PRO. -> PROC.
    assert _minimal_abbreviation("PRINT") == "P."
    assert _minimal_abbreviation("PROC") == "PRO."
    assert _minimal_abbreviation("END") is None  # shadowed by ENDPROC
