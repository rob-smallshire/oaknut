<p align="center">
  <img src="https://raw.githubusercontent.com/rob-smallshire/oaknut/master/docs/basic/_static/oaknut-basic-logo.png" alt="oaknut-basic" width="300">
</p>

# oaknut-basic

[![PyPI version](https://img.shields.io/pypi/v/oaknut-basic)](https://pypi.org/project/oaknut-basic/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-basic)](https://pypi.org/project/oaknut-basic/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-basic)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-basic/LICENSE)
[![Documentation](https://img.shields.io/badge/docs-online-blue)](https://rob-smallshire.github.io/oaknut/basic/)

**[Read the documentation](https://rob-smallshire.github.io/oaknut/basic/)** — getting started, the command reference, and the API.

Convert [BBC BASIC](https://en.wikipedia.org/wiki/BBC_BASIC) programs between
their compact on-disc *tokenised* form and a plain-text listing — the two
directions a real BBC Micro performs when you `LOAD` a program and `LIST` it —
plus line numbering for source typed without numbers.

## The problem

A tokenised BBC BASIC program is bytecode, not text: keywords like `PRINT` and
`GOTO` are single bytes, line numbers are packed into each line's header, and a
reference such as `GOTO 100` is scrambled into a three-byte form that can never
be mistaken for a line terminator. A text codec cannot read it; decoding one as
text produces garbage.

`oaknut-basic` reproduces the **BBC BASIC II** ROM's tokeniser and de-tokeniser
exactly — every token value, flag, and the line-number encoding — so a program
round-trips between bytes and text **byte-for-byte**.

## Installation

Install with the `[cli]` extra for the `oaknut-basic` command, or bare for the
library only:

```
uv tool install "oaknut-basic[cli]"     # the command-line tool
uv add oaknut-basic                       # the importable library
```

`pip` works identically with the same names. `oaknut-basic` requires Python
3.11 or newer.

## Command-line usage

```
$ oaknut-basic --help
Usage: oaknut-basic [OPTIONS] COMMAND [ARGS]...

  Tools for BBC BASIC source and tokenised programs.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  detokenise  De-tokenise a stored BBC BASIC program into source text.
  number      Prepend ascending line numbers to an unnumbered BBC BASIC...
  tokenise    Tokenise BBC BASIC source text into a stored program.
```

Every command reads from a file or standard input and writes to a file or
standard output, so each works file-to-file and as a pipe stage. That makes it
compose with [`oaknut-disc`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-disc)
to edit a program in place on a disc image:

```
disc get game.ssd MENU - | oaknut-basic detokenise > menu.bas
oaknut-basic tokenise menu.bas | disc put game.ssd MENU -
```

Tokenising and de-tokenising are exact inverses, so a program survives a
there-and-back trip unchanged. `tokenise` can also number unnumbered source on
the way in (`--start` / `--step`), exactly as typing it under `AUTO` would.

## Library usage

The library is function-shaped — `tokenise`, `detokenise`, and `number_lines`,
all importable from `oaknut.basic`:

```python
from oaknut.basic import tokenise, detokenise

program = tokenise('10 PRINT "HELLO"\n20 GOTO 10\n')   # str -> bytes
listing = detokenise(program)                          # bytes -> str
assert tokenise(detokenise(program)) == program        # byte-exact
```

When the program lives in a disc image, prefer the path-object wrappers
`DFSPath.read_basic` / `write_basic` (and the ADFS equivalents), which compose
the codec with the disc's character encoding and the correct load address.

## References

- [BBC BASIC](https://en.wikipedia.org/wiki/BBC_BASIC) — Wikipedia overview of
  the language and its versions.
- [BBC BASIC program format](https://beebwiki.mdfs.net/Program_format) —
  BeebWiki reference for the on-disc tokenised format and the token table.

## Part of oaknut

`oaknut-basic` is one package in the
[oaknut](https://github.com/rob-smallshire/oaknut) monorepo of tools for Acorn
computer filesystems, files, and formats. It backs the `read_basic` /
`write_basic` methods of the `oaknut-dfs` and `oaknut-adfs` packages, and is
usable on its own for `.bas` / `.bbc` files outside a disc image.

## License

MIT — see [LICENSE](LICENSE).
