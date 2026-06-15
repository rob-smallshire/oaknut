"""Minimal reproductions of known crunch discrepancies.

Round-tripping the real disc-image program corpus (see
``oaknut-dfs/tests/test_basic_corpus.py``) surfaced two ways our
tokeniser diverges from genuine BBC BASIC II bytes when a keyword abuts
another token or an identifier. Both are open questions about the exact
ROM crunch rule, pending confirmation against the disassembly; these
``xfail`` tests pin the expected (real-ROM) behaviour so they flip to
passing once the rule is implemented.
"""

import pytest
from oaknut.basic import tokenise

# Token bytes referenced below.
_DIV = 0x81
_TRUE = 0xB9
_ELSE = 0x8B


def _body(statement: str) -> bytes:
    program = tokenise("10" + statement)
    return program[4 : program[3]]


@pytest.mark.xfail(
    reason="a keyword embedded in an identifier-like run should tokenise: "
    "real BBC bytes have GDIV40 -> G, DIV, 40. The crunch rule for keyword "
    "matching inside a name is not yet pinned down.",
    strict=True,
)
def test_keyword_tokenises_mid_identifier():
    # From MasterWelcome.adl:$.Chardes — `Q=2-GDIV40` stores DIV as &81.
    assert _DIV in _body("Q=2-GDIV40")


@pytest.mark.xfail(
    reason="a conditional keyword immediately followed by another keyword "
    "should still tokenise: real BBC bytes have =TRUEELSE= -> =, TRUE, ELSE, "
    "=. We currently suppress TRUE because a name character (E) follows.",
    strict=True,
)
def test_conditional_keyword_before_another_keyword():
    # From L3-Utils.dsd:U.Init — `THEN=TRUEELSE=` stores TRUE &B9 then ELSE &8B.
    body = _body("IFA THEN=TRUEELSE=B")
    assert _TRUE in body and _ELSE in body
