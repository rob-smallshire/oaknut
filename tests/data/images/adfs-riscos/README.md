# RISC OS ADFS test corpus (New Map development)

Real ADFS disc images used to develop and test New Map / RISC OS (FileCore)
support in `oaknut-adfs`. These supplement the existing old-map corpus
(`adfs-linear/`, `data-centre/`), which is old map + old directory only.

## Provenance

Downloaded from the [4corn Computers archive](https://www.4corn.co.uk/), which
mirrors Acorn Computers' official FTP site. These are Acorn's own operating
system distribution discs — the standard preservation set, widely mirrored.

Source path: `archive/archiology/osdiscs/`.

## Classification

Established by decoding the on-disc structures per Gerald Holdsworth's
*Guide to Disc Formats* (`docs/dev/manuals/DiscImage.pdf`).

| File | Size | Map | Directory | Notes |
|---|---|---|---|---|
| `D_Arthur_Welcome.adf` | 800K | Old | New ("Hugo") | Arthur 1987 Welcome disc; new dir at 0x400, 1024-byte sectors |
| `D_RISCOS310_App1.adf` | 800K | Old | New ("Hugo") | RISC OS 3.10 core tools; D format |
| `E_RISCOS310_NewLook.adf` | 800K | New | New ("Nick") | RISC OS 3.10 NewLook kit; single-zone new map, disc record at 0x04 (log2secsize=10, nzones=1, idlen=15, log2bpmb=7, root=0x203 → 0x800) |

## Progression (oldest → newest, simplest → most complex)

The implementation builds up in this order; each rung adds one new subsystem:

1. **D** — old map + **New directory** (2048 B, "Hugo"/"Nick" tail). ← `D_*.adf`
2. **E** — **New map** (single zone) + New directory. ← `E_RISCOS310_NewLook.adf`
3. **F** — new map, **4 zones** + New directory. _(1.6MB specimen still to source)_
4. **E+/F+** — new map + **Big directories** ("SBPr"/"oven", name heap). _(to source)_
5. **New-map hard discs** — many zones, boot block at 0xC00. _(to source)_
6. **G** — 3.2MB octal-density big-dir floppy. _(to source; rare)_
