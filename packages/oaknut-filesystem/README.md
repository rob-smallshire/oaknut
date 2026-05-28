# oaknut-filesystem

The pluggable **filesystem contract** for the oaknut family — the base every
Acorn (and, in principle, foreign) filesystem plugs into.

A *filesystem* is the unit of extension: Acorn DFS, Watford DFS, Opus DDOS,
ADFS, AFS, … are peers, registered on the `oaknut.filesystem` entry-point axis
(built on `oaknut-extension`). Each one:

- **probes** an image region and proposes what it is — with a confidence,
  evidence, and a candidate *geometry*;
- **opens** a region into a mount exposing a small **core** (list / stat /
  read / write / exists, and parsing its own path syntax) plus opt-in
  **capability protocols** (`HierarchicalDirectories`, `AcornMetadata`,
  `BootOption`, `UserDatabase`, `RegionHost`);
- declares its **geometry grammar** — the physical layouts it supports.

Two concerns are kept strictly apart:

- **Geometry** — the *physical* mapping of image bytes to logical sectors
  (track count, sides, interleave, density, CHS). This is the discimage
  `DiscFormat` layer, *beneath* the filesystem.
- **Filesystem** — the *logical* structure that turns sectors into files and
  directories.

This package also hosts the **identification coordinator** (`identify()`): it
runs the registered filesystems over an image, ranks the candidates, and
recurses into reserved regions (an ADFS host's tail, where an AFS or other
filesystem may live) to produce a per-partition `Identification` tree.

It depends on **no** concrete filesystem package and imports none: filesystems
are discovered purely through entry points, so any subset can be installed and
the rest simply aren't handled.

See `docs/dev/filesystem-extensions.md` (architecture) and
`docs/dev/filesystem-extensions-plan.md` (implementation plan).
