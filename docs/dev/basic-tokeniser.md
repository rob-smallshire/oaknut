# BBC BASIC tokeniser and de-tokeniser — design and internals

How `oaknut-basic` converts between BBC BASIC source text and the
compact tokenised form the interpreter stores and runs. This is a
developer reference for the codec itself; for the user-facing API and
CLI see the [online manual](https://rob-smallshire.github.io/oaknut/basic/).

> **Scope: BBC BASIC II.** Every token value, flag bit, and tokenising
> rule below is specific to **BBC BASIC II** — the 16 KB language ROM of
> the BBC Micro. BASIC IV (Master) keeps the scheme but changes token
> values; BASIC V (Archimedes) uses a different, multi-byte scheme.
> Treat the *mechanism* as portable and the *values* as version II only.

The behaviour described here was established from two authoritative
sources, and is held to them by the test suite (see
[Validation against the ROM](#validation-against-the-rom)):

- an annotated disassembly of the BASIC II ROM (the
  `acornaeology/bbc-basic` analysis), which gives the token table, the
  flag semantics, and the routine-level behaviour; and
- [`basictool`](https://github.com/ZornsLemma/basictool), a 6502
  emulator that runs the genuine BASIC II ROM and so tokenises /
  de-tokenises exactly as a real machine does — used as a differential
  oracle at build time only.


## Module layout

Everything lives under `packages/oaknut-basic/src/oaknut/basic/`:

| Module | Responsibility |
|---|---|
| `tokens.py` | The keyword/token/flag table, the flag-bit constants, the token→keyword map, and program-storage limits. Pure data. |
| `linenumber.py` | The `&8D` three-byte line-number reference codec (`encode_line_number` / `decode_line_number`). |
| `tokeniser.py` | `tokenise(source)` — the line framer and the body "crunch" state machine. |
| `detokeniser.py` | `detokenise(data)` — the `LIST`-style walk back to text. |
| `numbering.py` | `number_lines` — `AUTO`-style line numbering, used by the `number` command and by `tokenise`'s auto-numbering. |
| `exceptions.py` | The categorised error hierarchy (`BASICError` → `TokeniseError` / `DetokeniseError`). |

The library core depends only on `oaknut-exception`. Character-set
conversion (Acorn ↔ UTF-8) is deliberately **not** here — the codec
works in code points (see [Character encoding](#character-encoding-and-the-code-point-boundary)).


## The on-disc program format

A tokenised program is a sequence of line records terminated by an
end-marker:

```
&0D <lineNo-hi> <lineNo-lo> <length> <body…>   …   &0D &FF
```

- `&0D` is a **start-of-line** marker (not an end marker).
- The line number is a 2-byte big-endian value in the header. Valid
  range is `0`–`32767` (see [Line-number references](#line-number-references-the-8d-codec)).
- `length` counts the **whole record** — from this `&0D` up to but not
  including the next one — so `length = 4 + len(body)`. It is a single
  byte, capping the body at **251 bytes** (`MAX_BODY_LENGTH`).
- The program ends with `&0D &FF` (an `&FF` where a line-number high
  byte would be). The empty program is exactly `&0D &FF`.

These constants live in `tokens.py` (`HEADER_LENGTH`,
`MAX_BODY_LENGTH`). Both the tokeniser (framing) and de-tokeniser
(walking) use them.


## The keyword/token table and flag bits

`tokens.py` holds the table as it appears in ROM, as a flat list of
`(keyword, token, flags)` triples in **ROM scan order**. Order is
significant — it resolves shared prefixes and abbreviations (see below).

- Tokens are single bytes in `&80`–`&FF`. There are **no multi-byte
  tokens** in BASIC II.
- `&8D` is the line-number reference token; it is **not** a table entry
  (it is produced and consumed specially).
- `&CE` is an unused gap — no keyword, no handler.
- The table has 126 entries. The tokeniser scans only the first **121**
  (it stops at `WIDTH`, whose token `&FE` doubles as the table-end
  sentinel). The five entries after it are the **assignment-form
  pseudo-variables** (`PTR`/`PAGE`/`TIME`/`LOMEM`/`HIMEM` as `&CF`–`&D3`);
  they are reachable only by the de-tokeniser, which needs them to
  render those tokens back to text. `KEYWORDS` is the scannable list;
  `TOKEN_TO_KEYWORD` covers all 126.

Each entry carries a **flag byte**. The bits, and where each is used:

| Bit | Mask | Meaning |
|---|---|---|
| 0 | `&01` | **Conditional.** Suppress a run-start match if a name character follows (so `TIME` does not shadow the variable `TIMER`). See [Rule B](#rule-b--conditional-keywords). |
| 1 | `&02` | **Middle-of-statement.** After emitting, go mid-statement and disarm the line-number flag. (Most commands.) |
| 2 | `&04` | **Start-of-statement.** After emitting, reset to start-of-statement and disarm. (`THEN`, `ELSE`, `ERROR`, `LET`.) |
| 3 | `&08` | **FN/PROC.** Do not tokenise the following identifier — skip the procedure/function name whole. |
| 4 | `&10` | **Line number follows.** Arm the line-number flag so the next decimal literal is `&8D`-encoded. (`GOTO`, `GOSUB`, `THEN`, `ELSE`, `RESTORE`, `LIST`, `DELETE`, `RENUMBER`, `TRACE`, `AUTO`.) |
| 5 | `&20` | **Stop tokenising.** Copy the rest of the line literally and return. (`REM`, `DATA`.) |
| 6 | `&40` | **Pseudo-variable.** At the start of a statement, add `&40` to the token to select the *assignment* form. |

A keyword with **no** state bits (flag `&00` or only the conditional
bit `&01`) is a *value keyword* — a function or operator word such as
`TO`, `DIV`, `GET$`, `RND`. These change neither the statement state nor
the line-number arm; that distinction is the crux of several edge cases
below.


## Line-number references: the `&8D` codec

A line number referenced *inside* a body — the target of `GOTO`,
`THEN`, etc. — is stored as `&8D` followed by three bytes. The encoding
lifts every byte into `&40`–`&FF` and gathers the dangerous high bits
into one scrambled control byte, so none of the three can collide with
`&0D` (the line terminator). `linenumber.py` implements both directions
exactly as the ROM does.

The codec is **many-to-one**: several encodings decode to the same line
number (some high bits are "don't care"). We always emit the canonical
form. This is why re-tokenising a program written with a *non-canonical*
encoding (by `RENUMBER`, or a foreign tool) can produce different —
though equivalent — bytes; see [Known limitations](#known-limitations).

The encoding round-trips for `0`–`32767`. Above that the high bit is
lost, which is the mechanism behind the 32767 line-number ceiling. The
tokeniser raises `LineNumberRangeError` for a referenced or leading
number above it rather than mis-encoding silently.


## The tokeniser ("crunch")

`tokenise(source)` does two things: it frames the program and it
crunches each line's body.

### Framing

Lines are split **strictly** on `\r\n` / `\r` / `\n` only —
*not* with `str.splitlines()`, which also breaks on `&0B`, `&0C`,
`&1C`–`&1E` and other Unicode line boundaries that occur legitimately
inside string literals (mode-7 / VDU control codes). Each non-blank line
must begin with a line number (whitespace before it is dropped); the
digits become the 2-byte header and the rest is the body. Auto-numbering
(`tokenise(source, start=, step=)`) numbers unnumbered source first, via
`number_lines`, and refuses input that already carries numbers.

### The body crunch: two pieces of state

The crunch (`_tokeniser._tokenise_body`) is a small state machine over
two flags, matching the ROM's zero-page `&3B`/`&3C`:

- **`mid`** — `False` at the *start of a statement*, `True` *mid-statement*.
  It selects a pseudo-variable's form and decides whether a leading `*`
  is OSCLI or multiply.
- **`armed`** — `True` when the next decimal literal should be
  `&8D`-encoded as a line-number reference.

**The body starts `mid = False`, `armed = True`.** The `armed = True`
is subtle and was the source of a real bug found by the ROM oracle: on
the real machine the *leading line number* is crunched with the
line-number flag pre-set, and encoding a number never clears it, so the
arm **carries over** into the body. Hence `10 TO1` stores `TO` then the
`&8D`-encoded `1`, while `10 PRINT1` stores `PRINT` then a literal `1`
(because `PRINT` disarms — see the transition tables).

### Keyword matching: three rules

#### Rule A — keywords match only at the start of a name run

`_try_keyword` is entered only at the start of a run of name characters
(`0-9 A-Z a-z _`). If the first character does not begin a keyword, the
whole run is swallowed as one identifier and keyword matching is **never
re-attempted inside it**. A fresh run — and a fresh match attempt —
begins at line start, after any non-name character, or right after an
emitted token.

Consequences:

- `GDIV40` is the literal identifier `GDIV40` — the interior `DIV` is
  never looked at. Likewise `GONE`, `STORE`, `SANDY`.
- `G DIV40` (space) is `G`, `[DIV]`, `40` — the space ends the run.
- `DIVMOD` is `[DIV][MOD]` — a token ends a run, so the next character
  starts a fresh one.

Matching scans the table in ROM order and takes the first **full** match.
A `.` in the source accepts an **abbreviation** of whatever entry the
typed letters first reach (so `P.`→`PRINT`, `PR.`→`PRINT`, `PRO.`→`PROC`);
the curated table order is what makes the shortest unambiguous
abbreviation resolve. A keyword shadowed at every prefix by an earlier
entry (`END` behind `ENDPROC`) has no abbreviation.

#### Rule B — conditional keywords

The conditional bit (`&01`) is checked *after* a full run-start match:
if a name character follows the keyword, the match is abandoned and the
run is read as an identifier. The conditional set is the "complete-word"
keywords (`TRUE`, `FALSE`, `TIME`, `PTR`, `PAGE`, `END`, `PI`, `RND`,
`COUNT`, …) — exactly the ones likely to be the leading substring of a
variable name. So `TIMER`, `TRUEELSE` and `ENDPROCPRINT` are all literal,
while `TRUE+` (operator follows) and `TRUE ELSE` (space, fresh run)
tokenise.

#### Pseudo-variables (bit 6)

`PTR`/`PAGE`/`TIME`/`LOMEM`/`HIMEM` tokenise to their **function** token
mid-statement and their **assignment** token (`+&40`) at the start of a
statement. The form is chosen using `mid` *at the moment the token is
emitted* — `X=PAGE` → `&90` (function), `PAGE=&2000` → `&D0` (assignment).

### State transitions

After each element the crunch updates the two flags. The full rules
(verified vector-for-vector against the ROM):

| Element | `mid` | `armed` |
|---|---|---|
| body start | `False` | **`True`** |
| space | — | — |
| comma | — | — |
| string `"…"` | — | — |
| `&hex` constant | `True` | — |
| `:` (separator) | `False` | `False` |
| name / identifier run | `True` | `False` |
| decimal number (not armed) | `True` | — |
| decimal number (armed → `&8D`) | `True` | — (stays armed) |
| operator / other character | `True` | `False` |
| keyword, bit 2 (START) | `False` | `False` |
| keyword, bit 1 (MIDDLE) | `True` | `False` |
| value keyword (flag `&00`/`&01`) | — | — |
| keyword, bit 4 (LINE NUMBER) | (per above) | `True` |
| `FN`/`PROC` (after a name) | `True` | `False` |

Reading these tables explains the tricky cases:

- `AND0` → `AND` is a value keyword (leaves `armed` set), so the `0`
  encodes. `PRINT1` → `PRINT` is bit-1 (disarms), so `1` is literal.
- `? ERR PAGE` → the operator `?` sets `mid`, so `PAGE` is the function
  form. `OPENOUT LOMEM` → `OPENOUT` is a value keyword (leaves `mid`
  alone), so `LOMEM` at statement start is the assignment form.
- A *string* leaves both flags alone: `"s" *` is still statement-leading
  OSCLI, and `"s" 1` still encodes the `1`.

### Suppression contexts

Tokenising is turned off and bytes copied verbatim:

- inside a string literal, through the closing `"` (or to end of line if
  it never closes — the rest stays literal, matching the ROM);
- after `REM` or `DATA` (bit 5) — to end of line, colons included;
- after a statement-leading `*` (OSCLI) — to end of line;
- across an `&` hex-digit run and a decimal/`.` number run.


### The greedy crunch (`crunch="greedy"`)

The ROM was not the only tokeniser to produce tokenised BBC BASIC. A
class of early-1980s commercial programs (the Voltmace Delta 14B drivers
`KEYPAD` and `JOYSTIK`, © Custom Video Productions, are the worked
examples) was crunched by a **greedier** third-party tool. Its output
de-tokenises fine — the byte format is the same — but re-tokenising that
source under the ROM crunch does not reproduce the original bytes,
because the greedy tool recognises keywords in three places the ROM does
not. `tokenise(..., crunch="greedy")` selects it; `"rom"` (the default)
is unchanged and stays byte-exact to the ROM.

The greedy crunch **is** the ROM crunch plus three localised rules — the
`_tokenise_body` state machine, keyword table, and every other rule above
are shared:

1. **A keyword interrupts a hex constant.** The ROM's hex loop copies
   every `0`–`9` / `A`–`F` unconditionally, so `&FE60ANDROW%` is the run
   `&FE60A` then the name `NDROW%`. The greedy loop breaks the run where a
   keyword begins (`_starts_keyword`), giving `&FE60`, `[AND]`, `ROW%`.
2. **An `FN`/`PROC` name breaks at a `FLAG_START` keyword.** The ROM's
   name-skip swallows every alphanumeric. The greedy skip keeps the first
   name character but ends the name at a following `THEN`/`ELSE`
   (`_starts_flag_start_keyword`) — and *only* those, so a function
   keyword embedded in a name (`READ` in `PROCREADKP`) is left intact:
   `PROCWTKEYELSEPROCBKKEY` → `[PROC]WTKEY`, `[ELSE]`, `[PROC]BKKEY`.
3. **Refined conditional suppression.** Rule B suppresses a conditional
   keyword whenever a name character follows; the greedy crunch suppresses
   it only when that character does not *itself* begin a keyword. So
   `STOPELSE` → `[STOP][ELSE]` (E begins `ELSE`), while `NEWKEY%` stays
   the literal `NEWKEY%` (K begins nothing).

This is a **distinct** tokeniser, greedier than *both* oaknut's default
and the ROM — the cross-referenced ROM routines (`.tok_hex_loop`,
`.tok_kw_found`, `.tok_skip_fnproc_loop`) do none of this. The two
commercial programs are the differential oracle: their own `detokenise`
output re-tokenises byte-for-byte under `crunch="greedy"`
(`tests/data/greedy/`, `tests/test_greedy_crunch.py`).


## The de-tokeniser

`detokenise(data)` mirrors the ROM's `LIST`: walk the program on its
`&0D` markers and, for each line, render the line number followed by the
de-tokenised body. Within a body (`_detokeniser._detokenise_body`):

- a keyword token expands to its table spelling (`TOKEN_TO_KEYWORD`),
  including the assignment-form `&CF`–`&D3`;
- a `&8D` reference decodes to plain decimal;
- a quote flag tracks string state; **inside a string every byte prints
  raw**, so a token-valued byte stays a character (never expands) — this
  also makes escaped `""` and unterminated strings behave like the ROM.

**Formatting difference (intentional).** The ROM's `LIST`
right-justifies the line number in a 5-character field; we render it as
plain decimal with no padding. The *bodies* are byte-identical — only
the line-number field differs — which keeps our output clean and
trivially re-tokenisable (the tokeniser drops leading whitespace before
the number). This is why `detokenise(tokenise(x)) == x` is **not**
guaranteed for source (abbreviations expand, line numbers re-render to
canonical form), while `tokenise(detokenise(p)) == p` **is** guaranteed
for any valid program.


## Character encoding and the code-point boundary

The codec works in `str` ↔ `bytes` pairs with **latin-1 / code-point
semantics**: a source character contributes the byte `ord(c)`, and a
stored byte `b` de-tokenises to `chr(b)`. The text carries no character
set of its own — code point `&60` is byte `&60`.

This keeps the core encoding-free and therefore byte-exact. Mapping code
points onto a real character set is a *caller-side* concern:

- the CLI bridges at its I/O boundary — `--encoding` (default `acorn`,
  the BBC set; or `utf-8`) decodes input and encodes output, and selects
  the line terminator (`\r` for `acorn`, `\n` otherwise);
- a library caller working on a disc image gets it from the path
  object's `read_basic` / `write_basic`.


## Validation against the ROM

The codec is held to the genuine ROM, not to anyone's reading of the
prose. There are four layers, all of which keep `basictool` strictly
**build-time** — no test imports it.

1. **ROM-generated golden vectors** (static, committed):
   - `tests/test_rom_golden.py` — `(source, tokenised-body)` pairs;
   - `tests/test_rom_golden_detokenise.py` — `(program, expected-text)` pairs.
   Regenerate with `scripts/gen_rom_golden.py` and
   `scripts/gen_rom_detok_golden.py` (each shells out to `basictool -2`;
   override its path with `$BASICTOOL`).

2. **The crunch-rule tests** (`tests/test_crunch_rules.py`) — the
   Rule A / Rule B / arm-carry vectors, each the exact body the ROM
   produces.

3. **Parameterised table coverage** (`tests/test_keyword_coverage.py`) —
   every keyword tokenises to its token, every token de-tokenises to its
   keyword, and every minimal abbreviation resolves.

4. **A real-program corpus regression test**
   (`packages/oaknut-dfs/tests/test_basic_corpus.py`, a cross-cutting
   suite as it needs DFS+ADFS to read the images) — every tokenised
   BASIC program in the disc-image corpus is round-tripped through the
   codec. The currently-passing set is pinned; any regression fails.

During development the two codecs were differentially fuzzed against
`basictool -2` over thousands of generated statements and the whole
corpus, reaching zero mismatches. The fuzzers themselves are not
committed (they are throwaway harnesses); the golden vectors and corpus
test capture the result permanently.


## Known limitations

These are properties of particular inputs, not codec defects, and are
why a handful of real programs in the corpus do not round-trip:

- **Foreign tokeniser.** Some programs contain keyword tokens *interior*
  to a name run (e.g. `G[DIV]40`), which BASIC II never produces. They
  were tokenised by a different BASIC — several are on a BBC Master disc
  (BASIC IV). Re-crunching under BASIC II rules correctly yields the
  literal form, so the bytes differ.
- **Non-canonical `&8D` encodings.** Written by `RENUMBER` or a tool;
  they decode correctly but re-encode to the canonical form.
- **Tokens after `REM`.** A program storing keyword tokens after a `REM`
  could not have come from the crunch (which stops at `REM`).
- **The `&CE` gap token.** No valid program contains it. We render it as
  its raw byte so a hand-crafted stream round-trips — a deliberate
  divergence from the ROM, whose `LIST` drops `&CE` entirely.


## Extending to other BASIC versions

The data/behaviour split is designed to make this mostly a data
exercise:

- **BASIC IV (Master)** keeps the scheme and the flag semantics but
  changes token values — largely a new `tokens.py` table.
- **BASIC V (Archimedes)** adds multi-byte tokens (`&C6`/`&C7`/`&C8`
  prefixes), which the crunch and the de-tokeniser walk would need to
  understand — a mechanism change, not just data.

Either way, `basictool` ships the relevant ROMs (`-2`/`-4`) and the
golden-vector generators take a `--basic`-equivalent flag's worth of
change, so a new version can be pinned to its own ROM the same way.
