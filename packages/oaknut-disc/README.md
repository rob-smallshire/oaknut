<p align="center">
  <img src="https://raw.githubusercontent.com/rob-smallshire/oaknut/master/docs/disc/_static/oaknut-disc-logo.png" alt="oaknut-disc" width="300">
</p>

# oaknut-disc

[![PyPI version](https://img.shields.io/pypi/v/oaknut-disc)](https://pypi.org/project/oaknut-disc/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-disc)](https://pypi.org/project/oaknut-disc/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-disc)](https://github.com/rob-smallshire/oaknut)
[![Documentation](https://img.shields.io/badge/docs-online-blue)](https://rob-smallshire.github.io/oaknut/disc/)

**[Read the documentation](https://rob-smallshire.github.io/oaknut/disc/)** — full walkthrough, cookbook, and command reference.

`disc` is a unified command-line tool for inspecting, extracting from, and
modifying [Acorn computer](https://en.wikipedia.org/wiki/Acorn_Computers) disc
images — Acorn DFS and Watford DFS floppies, ADFS floppies and hard discs,
Acorn Level 3 File Server (AFS) partitions, ROM Filing System (ROMFS) images,
and ZIP archives of Acorn files — through one consistent interface.

It recognises each format by content, with a filing-system prefix
(`dfs:`, `adfs:`, `afs:`) to route commands on dual-partition images, and Acorn
star-command aliases (`*CAT`, `*DELETE`, `*RENAME`, …) alongside their
Unix-named equivalents.

## Installation

`oaknut-disc` requires only [`uv`](https://docs.astral.sh/uv/), which handles
Python installation and virtual environments for you.

### Run without installing

```
uvx --from oaknut-disc disc <command> [options]
```

### Persistent install

```
uv tool install oaknut-disc
```

then invoke it as just `disc`:

```
disc <command> [options]
```

Or with pip:

```
pip install oaknut-disc
```

## Usage

```sh
# List the contents of a DFS floppy
disc ls 'games.ssd:$'

# Copy a file from a DFS floppy to an ADFS hard disc, mapping metadata across
disc cp 'games.ssd:$.ELITE' 'scsi0.dat:$.Elite'

# Create and initialise a Level 3 File Server disc (ADFS host + AFS tail)
disc create scsi0.dat --geometry capacity=10MB --title Server
disc afs init scsi0.dat --disc-name Server --user RJS:2MiB --emplace Library

# Walk both partitions of a dual ADFS + AFS hard disc
disc tree scsi0.dat
```

## License

MIT.
