# oaknut-file

[![PyPI version](https://img.shields.io/pypi/v/oaknut-file)](https://pypi.org/project/oaknut-file/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-file)](https://pypi.org/project/oaknut-file/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-file)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-file/LICENSE)

Acorn file metadata handling for the oaknut package family.

`oaknut-file` is the shared metadata layer used across the
[oaknut](https://github.com/rob-smallshire/oaknut) family — by
`oaknut-dfs`, `oaknut-adfs`, `oaknut-afs`, `oaknut-zip`, and the `disc`
CLI. It provides:

- The `Access` IntFlag enum for Acorn file attribute bytes
- The `AcornMeta` dataclass for load/exec addresses and attributes
- INF sidecar file parsing and formatting (traditional and PiEconetBridge variants)
- Filename metadata encoding (`,xxx`, `,llllllll,eeeeeeee`, `,load-exec`)
- Extended attribute read/write under `user.acorn.*` and `user.econet_*`

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv add oaknut-file
```

`pip install oaknut-file` also works.

The `xattr` package is automatically installed on macOS, where it is
required for extended attribute support. Linux uses `os.setxattr` from
the standard library and needs no additional dependency. Windows does
not support extended attributes; the xattr functions will raise on use.

## Quick start

### Access flags

The `Access` IntFlag enum represents the standard Acorn OSFILE attribute byte,
as stored in traditional `.inf` files and the `user.acorn.attr` extended
attribute. (PiEconetBridge's own `perm` byte uses a different layout; see
below.)

```python
from oaknut.file import Access

# Compose flags with bitwise OR
flags = Access.R | Access.W | Access.L
print(repr(flags))  # <Access.LWR: 11>
print(hex(flags))  # 0xb
```

| Flag | Value | Meaning |
|------|-------|---------|
| `Access.R`  | 0x01 | Owner read |
| `Access.W`  | 0x02 | Owner write |
| `Access.E`  | 0x04 | Owner execute |
| `Access.L`  | 0x08 | Locked — prevents delete, overwrite, and rename on the disc filing systems |
| `Access.PR` | 0x10 | Public read |
| `Access.PW` | 0x20 | Public write |

A `*RUN`-only file — one that may be `*RUN` but not `*LOAD`ed, the
cassette/ROM copy protection — is owner `E` without `R`, which
`Access.is_run_only` tests. It is a distinct axis from `Access.L`
(locked): a delete-locked disc file is not run-only. `Access.WR` and
`Access.LWR` are provided as convenience composites for the common
owner-read+write and locked-owner-read+write cases.

### INF sidecar files

Two INF sidecar formats are supported. `parse_inf_line()` auto-detects which
format a line uses, while `format_trad_inf_line()` and `format_pieb_inf_line()`
let you choose explicitly when writing.

Traditional `.inf` files are read and written per the
[Stardot INF format specification](https://github.com/stardot/inf_format/blob/main/inf_format_full.md),
with J.G. Harston's defaults
([Storing Acorn/BBC metadata on other systems](https://mdfs.net/Docs/Comp/BBC/Filing/Metadata))
where it leaves room: a missing access field means `&33`, a `Locked` or bare
`L` marker `&19`, and a missing exec address is the load address. Quoted and
percent-encoded names, the `TAPE` prefix, extra fields such as `CRC=` and
`NEXT` are understood, and six-digit DFS-style addresses (`FF0E00`) are
widened to `&FFFF0E00`.

PiEconetBridge's `perm` byte swaps the lock (`0x04`) and execute-only (`0x08`)
bits relative to the Acorn byte, and uses `0x80` for hidden. The PiEB INF and
`user.econet_perm` functions translate it, so callers always see the Acorn
byte.

```python
from oaknut.file import (
    Access,
    format_trad_inf_line,
    format_pieb_inf_line,
    parse_inf_line,
)

# Traditional INF: filename load exec length [attr]
trad = format_trad_inf_line(
    filename="HELLO",
    load_address=0x1900,
    exec_address=0x8023,
    length=0x100,
    attr=int(Access.R | Access.W),
)
print(trad)
# HELLO       00001900 00008023 00000100 03

# PiEconetBridge INF: owner load exec perm
pieb = format_pieb_inf_line(
    load_address=0xFFFFDD00,
    exec_address=0xFFFFDD00,
    attr=int(Access.R | Access.W | Access.L | Access.PR),
)
print(pieb)
# 0 ffffdd00 ffffdd00 17   (LWR/R in PiEB's own perm layout)

# Auto-detect format on parse (returns (source_label, AcornMeta))
source, meta = parse_inf_line(trad)
print(meta.load_address, meta.exec_address, meta.access)
# 6400 32803 3

source, meta = parse_inf_line(pieb)
print(hex(meta.load_address), hex(meta.access), hex(meta.infer_filetype()))
# 0xffffdd00 0x1b 0xfdd
```

### Filename metadata encoding

Three filename suffix conventions are supported for embedding load/exec
addresses or RISC OS filetypes in host filenames.

```python
from oaknut.file import parse_encoded_filename

# RISC OS filetype suffix (3 hex digits)
clean, meta = parse_encoded_filename("PROG,ffb")
print(clean, hex(meta.infer_filetype()))
# PROG 0xffb

# MOS load-exec suffix (variable-width hex)
clean, meta = parse_encoded_filename("PROG,1900-801f")
print(clean, hex(meta.load_address), hex(meta.exec_address))
# PROG 0x1900 0x801f
```

### Filetype-stamped load addresses

When a load address has its top 12 bits set to `0xFFF`, the next 12 bits
encode a RISC OS filetype.

```python
from oaknut.file import AcornMeta

meta = AcornMeta(load_address=0xFFFF0E10)
print(meta.is_filetype_stamped, hex(meta.infer_filetype()))
# True 0xf0e
```

### Extended attributes

```python
from oaknut.file import write_acorn_xattrs, read_acorn_xattrs

# Write to user.acorn.* namespace
write_acorn_xattrs(
    "myfile.bin",
    load_address=0x1900,
    exec_address=0x8023,
    attr=0x03,
)

# Read back (falls through to user.econet_* if user.acorn.* is absent)
meta = read_acorn_xattrs("myfile.bin")
print(meta.load_address, meta.exec_address, meta.access)
```

## Public API

| Module | Exports |
|--------|---------|
| `oaknut.file.access` | `Access`, `parse_access`, `parse_access_spec`, `format_access_hex`, `format_access_text` |
| `oaknut.file.access_convention` | `AccessConvention`, `AccessContext`, `FILE_CONTEXT`, `DIRECTORY_CONTEXT`, `translate_access` |
| `oaknut.file.pieb` | `PiEconetBridgeAccessConvention`, `PIEB_ACCESS` |
| `oaknut.file.meta` | `AcornMeta` |
| `oaknut.file.formats` | `MetaFormat`, `SOURCE_*` labels |
| `oaknut.file.inf` | `parse_inf_line`, `format_trad_inf_line`, `format_pieb_inf_line`, `read_inf_file`, `write_inf_file` |
| `oaknut.file.filename_encoding` | `parse_encoded_filename`, `build_filename_suffix`, `build_mos_filename_suffix` |
| `oaknut.file.xattr` | `read_acorn_xattrs`, `write_acorn_xattrs`, `read_econet_xattrs`, `write_econet_xattrs` |

All public symbols are also re-exported from the top-level `oaknut.file` package.

## License

MIT
