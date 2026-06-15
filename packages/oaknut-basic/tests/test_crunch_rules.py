"""ROM-validated tests of the crunch's keyword-matching rules.

The two rules that govern when a keyword is recognised, confirmed against
a 6502 emulation of the genuine BBC BASIC II ROM:

- **Rule A** — a keyword matches only at the *start* of a name run. A run
  of name characters (``0-9 A-Z a-z _``) that does not begin with a
  keyword is swallowed whole as an identifier; the crunch never re-tries
  keyword matching inside it. A new run — and a new match attempt —
  begins at line start, after any non-name character, or right after an
  emitted token. So ``GDIV40`` stays literal (the ``DIV`` is interior),
  but ``G DIV40`` and ``DIVMOD`` tokenise (each keyword starts a run).

- **Rule B** — the conditional flag (bit 0) rejects a *run-start* match
  when a name character follows, so the "complete-word" keywords (``TRUE``,
  ``TIME``, ``END``, ``PI``, ...) do not shadow identifiers that begin
  with them: ``TIMER`` and ``TRUEELSE`` are literal, while ``TRUE+`` and
  ``TRUE ELSE`` tokenise.

Each vector is the exact body the ROM produces, taken from the emulation.
"""

import pytest
from oaknut.basic import tokenise

# (source after the line number, expected tokenised body bytes). Every
# body begins with the space between "10" and the statement.
_VECTORS = [
    # Rule A — a keyword interior to a name run never tokenises.
    ("GDIV40", b" GDIV40"),
    ("GONE", b" GONE"),
    ("STORE", b" STORE"),
    ("SANDY", b" SANDY"),
    ("XPRINT", b" XPRINT"),
    # Run-start match — keyword emitted, rest of the run literal.
    ("TOTAL", b" \xb8TAL"),
    ("PRINTX", b" \xf1X"),
    ("FORM", b" \xe3M"),
    ("INPUTS", b" \xe8S"),
    # Arm carry-over: the leading line number leaves the line-number flag
    # set, and a value keyword (flag &00) does not clear it, so a following
    # digit is &8D-encoded (AND0 -> AND, [0]; TO1 -> TO, [1]). A bit-1
    # keyword (PRINT) disarms, so PRINT1 stays literal.
    ("AND0", b" \x80\x8dT@@"),
    ("TO1", b" \xb8\x8dTA@"),
    ("PRINT1", b" \xf11"),
    # A token ends a run, so the next character starts a fresh run.
    ("DIVMOD", b" \x81\x83"),
    ("TOPRINT", b" \xb8\xf1"),
    ("TOELSE", b" \xb8\x8b"),
    # Rule B — conditional keyword followed by a name char stays literal.
    ("TIMER", b" TIMER"),
    ("TRUER", b" TRUER"),
    ("TRUEELSE", b" TRUEELSE"),
    ("TIMEPRINT", b" TIMEPRINT"),
    ("FALSEAND", b" FALSEAND"),
    ("PIAND", b" PIAND"),
    ("ENDPROCPRINT", b" ENDPROCPRINT"),
    # Rule B — a non-name character after the keyword lets it tokenise.
    ("TRUE+", b" \xb9+"),
    # Conditional + pseudo-variable: '=' is not a name char, so TIME
    # tokenises, and at statement start bit 6 gives the assignment form.
    ("TIME=0", b" \xd1=0"),
    # A space ends the run, so the following keyword starts a fresh one.
    ("G DIV40", b" G \x8140"),
    ("=TRUE ELSE=", b" =\xb9 \x8b="),
]


@pytest.mark.parametrize(("source", "expected_body"), _VECTORS, ids=[v[0] for v in _VECTORS])
def test_crunch_matches_basic_ii_rom(source, expected_body):
    program = tokenise("10 " + source)
    assert program[4 : program[3]] == expected_body
