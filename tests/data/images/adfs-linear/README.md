# Linearly-imaged 640K ADFS

`BCPL.adf` is a 640 KiB ADFS-L disc (the Acorn BCPL release) laid out in
**linear logical-sector order** — sector N at byte N × 256 — rather than
the interleaved `.adl` layout that BeebEm and other emulators emit (where
the two sides alternate per track).

Both layouts share the same size, and the root directory and free-space
map live entirely in track 0 side 0, where the layouts coincide. The two
only diverge once a directory's sectors cross a track boundary, so the
mismatch stays hidden until a command descends: read as interleaved, this
disc's `$.Library` yields a directory tail of `faul`.

Sourced from a Stardot forum thread (topic 13420). Kept as the regression
fixture for content-based 640K layout disambiguation and for the
directory-tree traversal checks in `validate` / `identify`.
