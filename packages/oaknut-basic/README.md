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

Work with the persistent artefacts a [BBC BASIC](https://en.wikipedia.org/wiki/BBC_BASIC)
program leaves behind — both the **code** and the **data**:

- **Programs.** Convert a program between its compact on-disc *tokenised* form
  and a plain-text listing — the two directions a real BBC Micro performs when
  you `LOAD` and `LIST` it — plus line numbering for source typed without
  numbers.
- **Data files.** Read and write the channel-based files a program creates with
  `OPENOUT` and writes with `PRINT#` and `BPUT#`, translating their tagged
  records to and from native Python values.

## The problem

Both formats are bytecode, not text, and idiosyncratic to the BBC.

A tokenised program packs keywords like `PRINT` and `GOTO` into single bytes,
folds line numbers into each line's header, and scrambles a reference such as
`GOTO 100` into a three-byte form that can never be mistaken for a line
terminator. A text codec decoding one produces garbage.

A `PRINT#` data file is just as surprising: `PRINT#channel, 42` writes a type
tag and the number's bytes **in reverse**, not the characters `4` `2`; strings
go out length-prefixed and backwards, and reals use the BBC's packed 5-byte
floating-point format. The file is meant to be read back only by `INPUT#`.

`oaknut-basic` reproduces the **BBC BASIC II** ROM's behaviour exactly — every
token value and flag, the line-number encoding, the record tags and the 5-byte
REAL format — so a program round-trips between bytes and text **byte-for-byte**,
and a data file round-trips through Python values **byte-for-byte**.

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

  Tools for BBC BASIC programs and data files.

Options:
  --version  Show the version and exit.
  --help     Show this message and exit.

Commands:
  data        Read and write BBC BASIC data files.
  detokenise  De-tokenise a stored BBC BASIC program into source text.
  number      Prepend ascending line numbers to an unnumbered BBC BASIC...
  tokenise    Tokenise BBC BASIC source text into a stored program.
```

The program commands read from a file or standard input and write to a file or
standard output, so each works file-to-file and as a pipe stage. That makes
them compose with [`oaknut-disc`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-disc)
to edit a program in place on a disc image:

```
disc get game.ssd MENU - | oaknut-basic detokenise > menu.bas
oaknut-basic tokenise menu.bas | disc put game.ssd MENU -
```

Tokenising and de-tokenising are exact inverses, so a program survives a
there-and-back trip unchanged. The `tokenise` command can also number
unnumbered source on the way in (`--start` / `--step`), exactly as typing it
under `AUTO` would.

The `data` subcommands turn a `PRINT#` data file into something host tools can
read. The `inspect` command shows its records as a table; `decode` and `encode`
are a lossless JSON round-trip pair for editing or generating a file:

```
oaknut-basic data inspect scores.dat
oaknut-basic data decode scores.dat | jq '.[0]'
echo '[42, "HELLO", 3.5]' | oaknut-basic data encode - scores.dat
```

## Library usage

Programs are handled by the functions `tokenise`, `detokenise`, and
`number_lines`, all importable from `oaknut.basic`:

```python
from oaknut.basic import tokenise, detokenise

program = tokenise('10 PRINT "HELLO"\n20 GOTO 10\n')   # str -> bytes
listing = detokenise(program)                          # bytes -> str
assert tokenise(detokenise(program)) == program        # byte-exact
```

When the program lives in a disc image, prefer the path-object wrappers
`DFSPath.read_basic` / `write_basic` (and the ADFS equivalents), which compose
the codec with the disc's character encoding and the correct load address.

Data files are handled by a context-managed, file-like object. The
module-level `open` mirrors the built-in one: a `mode` string selects a reader,
a writer, or a combined object, and accepts a path or a binary stream. The
polymorphic `write` picks the record type from the Python value; typed
`read_int` / `read_float` / `read_str` read it back without coercion:

```python
from oaknut.basic import datafile

with datafile.open("scores.dat", "w") as f:
    f.write("ALICE")     # str   -> string record
    f.write(42)          # int   -> integer record
    f.write(3.5)         # float -> real record

with datafile.open("scores.dat", "r") as f:
    for value in f:      # yields "ALICE", 42, 3.5
        print(value)
```

Strings use the BBC `acorn` character set by default, and reals convert through
the packed 5-byte REAL format exposed as `pack_float5` / `unpack_float5`.

## References

- [BBC BASIC](https://en.wikipedia.org/wiki/BBC_BASIC) — Wikipedia overview of
  the language and its versions.
- [BBC BASIC program format](https://beebwiki.mdfs.net/Program_format) —
  BeebWiki reference for the on-disc tokenised format and the token table.
- [Format of a random access file](https://beebwiki.mdfs.net/Acorn_DFS_disc_format) —
  BeebWiki background on the disc filing system that holds these files; the
  `PRINT#` record tags and 5-byte REAL format are documented in this package's
  own API reference.

## Part of oaknut

`oaknut-basic` is one package in the
[oaknut](https://github.com/rob-smallshire/oaknut) monorepo of tools for Acorn
computer filesystems, files, and formats. It backs the `read_basic` /
`write_basic` methods of the `oaknut-dfs` and `oaknut-adfs` packages, and is
usable on its own for the `.bas` / `.bbc` programs and the data files BBC BASIC
leaves on a disc.

## License

MIT — see [LICENSE](LICENSE).
