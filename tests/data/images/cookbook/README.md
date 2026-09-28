# Cookbook example corpus

Disc images consumed by the runnable CLI cookbook recipes under
`scripts/cli-examples/`. The directive that embeds those recipes
into the manual is `.. cli-example::` (defined in
`docs/disc/conf.py`); the helper that pulls an image out of this
directory into the recipe's working dir is `copy_from_corpus()`
(in `scripts/cli_example_helper.py`).

## Scope

The default for cookbook recipes is to **synthesise their own
inputs** from scratch — `disc create` + `disc put` is fast,
deterministic, and adds no bytes to the repo. Drop an image into
this directory only when:

- The scenario is *meaningfully* easier to demonstrate against a
  prepared image than against a synthetic one (e.g. a populated
  Level 3 File Server hard disc with several users and library
  directories).
- The image's content is **public-domain or synthetic**. Captured
  BBC games, commercial demo discs, or anything with unclear
  provenance does not belong here. The corpus ships in the
  repository under the project's MIT licence.

## Naming

Use a kebab-case file name that hints at what the image
demonstrates: `l3fs-populated.dat`, `dual-partition-empty.dat`,
`watford-ddfs-62-files.ssd`. The name appears unchanged in the
recipe (`copy_from_corpus("l3fs-populated.dat")`) so it is worth
spending a few seconds choosing.

## Discovery

`copy_from_corpus(name)` looks up the image by file name in this
directory. If you rename an image, update the recipes that
reference it; the docs build with `-W` fails loud on a missing
image so you cannot silently break a recipe.

## Provenance

- `l3v126.ssd` — the Acorn Level 3 File Server version 1.26 release disc,
  unmodified, from the mmbeeb/L3V126 repository's `MML3V126` release:
  <https://github.com/mmbeeb/L3V126/releases/tag/MML3V126>
  (SHA-256 `0c9ebd5e5cc5200262f5951431fed8f0b3bbe7d2d0ed19242ddac76c99099107`).
  The executable on it is `$.FS`. Keep the disc exactly as released, so
  the recipes match what readers download; recipes install the executable
  as `$.FS3v126`, the community's conventional name for the 1.26 server.
