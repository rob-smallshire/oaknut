# oaknut-afs

[![PyPI version](https://img.shields.io/pypi/v/oaknut-afs)](https://pypi.org/project/oaknut-afs/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-afs)](https://pypi.org/project/oaknut-afs/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-afs)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-afs/LICENSE)

A Python library for reading, writing, and creating
[Acorn Level 3 File Server](https://en.wikipedia.org/wiki/Acorn_Econet) (AFS)
disc partitions — the private on-disc filesystem the Level 3 File Server
served to BBC Micro, Master, and Archimedes clients over
[Econet](https://en.wikipedia.org/wiki/Econet).

AFS is a hierarchical, multi-user filesystem: it has real directories, a
per-file owner and public access model, and a `$.Passwords` file of user
accounts. It is identified by the `AFS0` magic in its info sectors.

> **Part of a dual-partition disc.** An AFS filesystem does not occupy a disc
> alone — it lives in the *tail cylinders* of an old-map
> [ADFS](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-adfs)
> disc. The real `WFSINIT` utility (and oaknut's `initialise()`) shrinks the
> ADFS partition and carves the AFS region out of the space freed. oaknut-afs
> reads and writes that region; oaknut-adfs handles the host.

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## What it does

- **Read and write** an AFS partition: browse the directory tree, read and
  write files, create and remove directories, and edit metadata (owner and
  public access, the native two-byte datestamp).
- **Partition and initialise** (`initialise()`): the `WFSINIT` analogue —
  repartition an old-map ADFS disc and lay down an empty AFS filesystem in the
  tail, with its map, root, and `$.Passwords` file.
- **Manage users** (`UserSpec`, `PasswordsFile`): create accounts with
  passwords and disc-space allocations; the built-in `Syst`, `Boot`, and
  `Welcome` accounts are handled.
- **Import a host tree** (`import_host_tree()`): populate a new filesystem from
  a directory of files with `.inf` sidecars.
- **Merge** (`merge()`) two AFS partitions, and **emplace shipped libraries**
  (`SHIPPED_LIBRARIES`) such as the standard `Library`.

Passwords are stored as the file server stored them: up to six cleartext ASCII
bytes in `$.Passwords`, with no encryption — oaknut reproduces the format
faithfully rather than obscuring it.

## Installation

```sh
uv add oaknut-afs         # or: pip install oaknut-afs
```

oaknut-afs works with any [PEP 517](https://peps.python.org/pep-0517/) build
front-end and package manager; the examples use
[`uv`](https://docs.astral.sh/uv/).

## Usage

### Creating and populating a filesystem

```python
from oaknut.afs import AFS, UserSpec

with AFS.create_file(
    "server.dat",
    capacity="10MB",
    disc_name="Server",
    users=[UserSpec(name="RJS", quota="2MB")],
) as afs:
    # Creating the RJS account also creates its home directory, $.RJS.
    (afs.root / "RJS" / "ReadMe").write_text("Welcome to the file server.\n")
```

### Reading

```python
from oaknut.afs import AFS

with AFS.from_file("server.dat") as afs:
    for entry in afs.root.iterdir():
        print(entry.name)
    text = (afs.root / "RJS" / "ReadMe").read_text()
```

For dual ADFS + AFS discs, the
[`disc`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-disc)
CLI reaches the AFS partition through the ADFS host with an `afs:` prefix
(`disc ls 'server.dat:afs:$'`), routed by content identification.

## Development

The package is developed in the
[oaknut](https://github.com/rob-smallshire/oaknut) workspace. From the
repository root:

```sh
uv sync                                  # install all workspace members editable
uv run pytest packages/oaknut-afs/tests  # this package's tests
uv run ruff check                        # lint
```

## Architecture

oaknut-afs depends on `oaknut-adfs` (to place and read the partition within its
ADFS host), `oaknut-discimage`, and `oaknut-file`, and contributes AFS to the
`oaknut.filesystem` extension axis so that AFS partitions are identified,
listed, and read through the `disc` CLI alongside the disc-based filing
systems. Sector-level access comes from
[`oaknut-discimage`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-discimage);
metadata and the `acorn` codec from
[`oaknut-file`](https://github.com/rob-smallshire/oaknut/tree/master/packages/oaknut-file).

## Further reading

- [AFS0 on-disc format](https://www.heyrick.eu/econet/fs/afs0.html) — Rick
  Murray's notes on the Level 3 File Server's private format.
- [Acorn Econet](https://en.wikipedia.org/wiki/Econet) — the network the file
  server served over.

## License

MIT — see [LICENSE](LICENSE).
