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
- Filename metadata encoding (`,xxx` and `,load-exec`; `,llllllll,eeeeeeee` read too)
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
print(repr(flags))
print(hex(flags))
```

Output:

```text
<Access.LWR: 11>
0xb
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
widened to `&FFFF0E00`. A name is held in its medium's own character set:
`format_trad_inf_line`, `parse_inf_line` and `read_inf_file` take that
codec as `encoding` (for example `"acorn"` for DFS, where `£` is byte `&60`),
and `export_with_metadata` and `import_with_metadata` take it as
`name_encoding`. Each defaults to Latin-1.

PiEconetBridge's `perm` byte swaps the lock (`0x04`) and execute-only (`0x08`)
bits relative to the Acorn byte, and uses `0x80` for hidden. The PiEB INF and
`user.econet_perm` functions translate it, so callers always see the Acorn
byte.

```python
from oaknut.file import (
    Access,
    format_pieb_inf_line,
    format_trad_inf_line,
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

# PiEconetBridge INF: owner load exec perm, in PiEB's own perm layout
pieb = format_pieb_inf_line(
    load_address=0xFFFFDD00,
    exec_address=0xFFFFDD00,
    attr=int(Access.R | Access.W | Access.L | Access.PR),
)
print(pieb)

# Auto-detect the dialect on parse; access comes back as the Acorn byte
source, meta = parse_inf_line(trad)
print(source, hex(meta.load_address), hex(meta.exec_address), hex(meta.access))

source, meta = parse_inf_line(pieb)
print(source, hex(meta.load_address), hex(meta.access), hex(meta.infer_filetype()))
```

Output:

```text
HELLO       00001900 00008023 00000100 03
0 ffffdd00 ffffdd00 17
inf-trad 0x1900 0x8023 0x3
inf-pieb 0xffffdd00 0x1b 0xfdd
```

### Filename metadata encoding

Three filename suffix conventions are read for embedding load/exec
addresses or RISC OS filetypes in host filenames: `,xxx` (a filetype),
`,load-exec` (as RISC OS HostFS and LanManFS write untyped files) and
`,llllllll,eeeeeeee` (as python-zipinfo-riscos writes them). Writing uses
the first two. A load address such as `&FFFF1900` carries the RISC OS
filetype marker, so pass `typed_metadata=False` for files from an 8-bit
filing system to keep their addresses.

```python
from oaknut.file import AcornMeta, build_filename_suffix, parse_encoded_filename

# RISC OS filetype suffix (3 hex digits)
clean, meta = parse_encoded_filename("PROG,ffb")
print(clean, hex(meta.infer_filetype()))

# Load-exec suffix (variable-width hex), as HostFS and LanManFS write it
clean, meta = parse_encoded_filename("PROG,1900-801f")
print(clean, hex(meta.load_address), hex(meta.exec_address))

# Writing: ,xxx for a filetyped file, ,load-exec otherwise
print(build_filename_suffix(AcornMeta(load_address=0xFFFFFB00, exec_address=0)))
print(build_filename_suffix(AcornMeta(load_address=0x1900, exec_address=0x8023)))

# &FFFF1900 carries the filetype marker; say when the words are addresses
io_meta = AcornMeta(load_address=0xFFFF1900, exec_address=0xFFFF8023)
print(build_filename_suffix(io_meta))
print(build_filename_suffix(io_meta, typed_metadata=False))
```

Output:

```text
PROG 0xffb
PROG 0x1900 0x801f
,ffb
,1900-8023
,f19
,ffff1900-ffff8023
```

### Filetype-stamped load addresses

When a load address has its top 12 bits set to `0xFFF`, the next 12 bits
encode a RISC OS filetype.

```python
from oaknut.file import AcornMeta

meta = AcornMeta(load_address=0xFFFF0E10)
print(meta.is_filetype_stamped, hex(meta.infer_filetype()))
```

Output:

```text
True 0xf0e
```

### Extended attributes

```python
from pathlib import Path

from oaknut.file import read_acorn_xattrs, write_acorn_xattrs

Path("myfile.bin").write_bytes(b"data")

# Write to the user.acorn.* namespace
write_acorn_xattrs(
    "myfile.bin",
    load_address=0x1900,
    exec_address=0x8023,
    attr=0x03,
)

# Read back (falls through to user.econet_* if user.acorn.* is absent)
meta = read_acorn_xattrs("myfile.bin")
print(hex(meta.load_address), hex(meta.exec_address), hex(meta.access))
```

Output:

```text
0x1900 0x8023 0x3
```

## Public API

| Module | Exports |
|--------|---------|
| `oaknut.file.access` | `Access`, `parse_access`, `parse_access_spec`, `format_access_hex`, `format_access_text` |
| `oaknut.file.access_convention` | `AccessConvention`, `AccessContext`, `FILE_CONTEXT`, `DIRECTORY_CONTEXT`, `translate_access` |
| `oaknut.file.pieb` | `PiEconetBridgeAccessConvention`, `PIEB_ACCESS` |
| `oaknut.file.meta` | `AcornMeta` |
| `oaknut.file.formats` | `MetaFormat`, `DEPRECATED_META_FORMATS`, `SOURCE_*` labels |
| `oaknut.file.inf` | `parse_inf_line`, `format_trad_inf_line`, `format_pieb_inf_line`, `read_inf_file`, `write_inf_file` |
| `oaknut.file.filename_encoding` | `parse_encoded_filename`, `build_filename_suffix`, `build_loadexec_filename_suffix` (`build_mos_filename_suffix` is a deprecated alias) |
| `oaknut.file.xattr` | `read_acorn_xattrs`, `write_acorn_xattrs`, `read_econet_xattrs`, `write_econet_xattrs` |

All public symbols are also re-exported from the top-level `oaknut.file` package.

## License

MIT
