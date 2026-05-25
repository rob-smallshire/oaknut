<p align="center">
  <a href="https://rob-smallshire.github.io/oaknut/disc/"><img src="docs/disc/_static/oaknut-disc-logo.png" alt="oaknut disc" width="280"></a>
  &nbsp;&nbsp;
  <a href="https://rob-smallshire.github.io/oaknut/zip/"><img src="docs/zip/_static/oaknut-zip-logo.png" alt="oaknut zip" width="280"></a>
</p>

# oaknut

Python tools for Acorn computer filesystems, files, and formats — the BBC Micro, Electron, Archimedes, and their descendants.

oaknut is a [`uv`](https://github.com/astral-sh/uv) workspace monorepo of independently published `oaknut-*` packages that share a single `oaknut.` Python namespace. Two of them are the tools most people come for, and each has its own manual.

## oaknut-disc

The unified `disc` command-line tool for inspecting, extracting from, and modifying Acorn disc images — DFS and Watford DDFS floppies, ADFS floppies and hard discs, and Acorn Level 3 File Server (AFS) partitions — through one consistent interface.

Documentation: **[the oaknut-disc manual](https://rob-smallshire.github.io/oaknut/disc/)** — installation, a CLI walkthrough, a cookbook, and the Python API reference.

## oaknut-zip

Read ZIP archives that carry Acorn file metadata — the load and execution addresses, access bits, and RISC OS filetypes that ordinary unzip tools discard.

Documentation: **[the oaknut-zip manual](https://rob-smallshire.github.io/oaknut/zip/)** — getting started and the API reference.

## Packages

Install whichever you need from PyPI. The bare `oaknut` distribution is an empty namespace placeholder, so install a specific `oaknut-*` package instead.

| PyPI distribution | Import path | Scope |
|---|---|---|
| [`oaknut-file`](packages/oaknut-file/) | `oaknut.file` | Acorn file metadata handling: INF sidecars, filename encoding, xattrs, and access flags |
| [`oaknut-discimage`](packages/oaknut-discimage/) | `oaknut.discimage` | Disc image sector abstractions shared by Acorn filesystem packages |
| [`oaknut-basic`](packages/oaknut-basic/) | `oaknut.basic` | BBC BASIC tokeniser and detokeniser for Acorn 8-bit and 32-bit BASIC source files |
| [`oaknut-dfs`](packages/oaknut-dfs/) | `oaknut.dfs` | Python library for handling Acorn DFS disc images (SSD/DSD format) |
| [`oaknut-adfs`](packages/oaknut-adfs/) | `oaknut.adfs` | Acorn ADFS disc image support for Archimedes, RISC OS, and BBC Master |
| [`oaknut-zip`](packages/oaknut-zip/) | `oaknut.zip` | Work with ZIP files containing Acorn computer metadata |
| [`oaknut-afs`](packages/oaknut-afs/) | `oaknut.afs` | Acorn Level 3 File Server (AFS) filesystem support — the private on-disc format WFSINIT prepares in the tail of an old-map ADFS disc |
| [`oaknut-disc`](packages/oaknut-disc/) | `oaknut.disc` | CLI for working with Acorn DFS, ADFS, and AFS disc images |
| [`oaknut-exception`](packages/oaknut-exception/) | `oaknut.exception` | Categorised exceptions and CLI error-reporting boundary for the oaknut package family |

The dependency arrows run strictly bottom-up: `file → discimage → {dfs, adfs} → afs`, with `basic` feeding into `dfs` and `adfs`, and `zip` depending only on `file`. The `disc` CLI package depends on all library packages.

## Development

Clone the repo, run `uv sync`, then `uv run pytest`. The workspace wires sibling packages as local path dependencies, so a change in one is immediately visible to the others. Contributor guidance is in [`CLAUDE.md`](CLAUDE.md) (with package-specific addenda under `packages/<name>/`), and architecture notes in [`docs/dev/`](docs/dev/).

## Licence

MIT. See each package's `LICENSE` file.
