# oaknut-romfs

Acorn ROM Filing System (ROMFS) support for the [oaknut](https://github.com/rob-smallshire/oaknut)
family of packages.

ROMFS is the filing system for paged ROMs on the BBC Micro and Acorn
Electron — sideways ROMs and cartridges. It stores files in the same
block layout as the Cassette Filing System (CFS), with the ROM image
standing in for the tape: each file is a chain of CFS-format blocks
carrying Acorn load and execution addresses, a block number, a length,
a flag byte, and header and data CRCs, introduced by a standard
paged-ROM service header.

The medium is read-only ROM, so the filing system is flat: there are no
directories, and a file's metadata is the load/exec pair plus a lock
bit, exactly as on cassette.

This package contributes ROMFS to the `oaknut.filesystem` extension axis,
so ROMFS images are identified, listed and read through the `disc` CLI
alongside the disc-based filing systems.

## Status

Pre-alpha. The package is being built up format-first: see
[`docs/romfs-format-spec.md`](docs/romfs-format-spec.md) for the on-ROM
byte layout and [`docs/architecture.md`](docs/architecture.md) for the
package design and its mapping onto the `oaknut.filesystem` contract.

## Installation

```sh
uv add oaknut-romfs
```

## Licence

MIT — see [LICENSE](LICENSE).
