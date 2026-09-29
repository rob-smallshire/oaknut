# File access: the canonical model and translation conventions

Status: design agreed 2026-09-28. Step 1 (the conventions layer) implemented
2026-09-29; see *As built* at the end.

This note defines how oaknut represents file access and translates it
between filing systems, so that every command which moves or displays a
file (`cp`, `put`, `get`, `import`, `export`, `gather`, `ls`, `stat`,
`chmod`, AFS host import, ZIP extraction) applies the **same** rules. It
covers the Acorn filing systems oaknut supports today, and is built to
accommodate the formats it is likely to support later: CP/M (Z80 second
processor), DOS/FAT including DR DOS (80186 second processor / Master
512), and the host's own permissions on Unix and Windows.

## Why

The rules are currently spread across the codebase and partly
duplicated:

| Rule | Where | Copies |
|---|---|---|
| DFS export (locked → `L\|W\|R`) | `DFSStat.access` (`oaknut.dfs`); `_DFS_DEFAULT_ACCESS` in `oaknut.file.access_mapping` | 2 — both wrong in the same way (#57) |
| DFS import (keep `L`) | `_coerce_access_to_locked` (`dfs.py`); DFS adapter `set_acorn_meta` | 2 |
| ADFS | `ADFSStat.access`; its own `_coerce_access_to_locked` | 1–2; public E dropped |
| AFS | `AFSAccess.from_acorn` / `to_acorn`; hand-rolled again in `afs/host_import.py` | 2 |
| ROMFS run-only | adapter maps `run_only ↔ Access.X` | 1 |

A single wrong rule (#57, reported by J.G. Harston) hid in plain sight
because it lived in a stat property that every consumer silently
inherited. Adding CP/M, FAT and host permissions to that arrangement
would multiply the problem.

## Sources

- BeebWiki, *File access* — <https://beebwiki.mdfs.net/File_access>: the
  bit definitions, the DFS read/write rules, directories, the private bit,
  and the DOS, CP/M and Unix mapping tables reproduced below.
- J.G. Harston on DFS export/import —
  <https://stardot.org.uk/forums/viewtopic.php?p=493553#p493553>.

Each convention below cites the table it implements.

## 1. The canonical attribute word

`oaknut.file.Access` is the single interchange representation. It is the
**Acorn attribute word**: the standard OSFILE access byte in bits 0–7,
extended with the RISC OS DOSFS / Win95FS attribute bits 8–10.

| Bit | Name | Meaning |
|---|---|---|
| 0 | `R` | owner may read (also `*RUN`, `*/`) |
| 1 | `W` | owner may write (`BPUT`, `OSGBPB`) |
| 2 | `E` | owner may execute |
| 3 | `L` | owner may **not** delete, rename or overwrite (locked) |
| 4 | `PR` | public may read |
| 5 | `PW` | public may write |
| 6 | `PE` | public may execute |
| 7 | `PL` | public locked / private — see below |
| 8 | `SYSTEM` | DOS/CP/M System attribute |
| 9 | `HIDDEN` | DOS Hidden attribute |
| 10 | `ARCHIVE` | DOS/CP/M Archive attribute |

Rules carried with the model:

- **A set bit means the right is present.** The *Advanced User Guides*
  document them inverted; that is wrong (BeebWiki).
- **Two principals, owner and public.** Every mapping on BeebWiki —
  including Unix, whose group and world both come from public — folds into
  these two. Unix group is derived by convention, not stored.
- **Run-only is `E` without `R`** (`access AND 5 = 4`), not a separate
  bit. ROMFS/CFS copy protection maps to that. `Access.X = 0x40` is
  retired: it collides with public E, so a run-only ROMFS file currently
  exports to `.inf` as "public execute". Retiring it is the one breaking
  change (deprecated alias first).
- **Bit 7 is not portable.** HADFS stores a private bit there, NFS returns
  a copy of `L`, and a non-owner can never delete in any case. Per
  BeebWiki, *unless copying within the same filing system, bit 7 is
  ignored* — conventions drop it on the way out unless the destination
  shares the source's family (§4).
- **Bits 8–10 are optional.** Acorn filing systems ignore them; only
  conventions that understand them read or write them.
- **Serialisation.** Traditional `.inf` and the `user.acorn.attr` xattr
  carry the low byte, as today. Bits 8–10 travel only where a format can
  hold them. What a sidecar holds is always a canonical value, never a
  native one.

Not part of the access model: CP/M **user numbers** (0–15) and the DOS
**Volume** / **Directory** attributes. User numbers are a namespace,
like a directory, and belong to paths. Volume and Directory describe what
an object *is*.

## 2. Conventions

A **convention** is a named, documented mapping between one native
attribute representation and the canonical word, in both directions. It
is the only place a filing system's access rules live.

```python
@dataclass(frozen=True)
class AccessContext:
    """What a convention may need to know besides the bits."""

    is_directory: bool
    filetype: int | None = None  # e.g. &FE6 UnixEx, for UnixFS x bits


class AccessConvention(Protocol):
    name: str  # "acorn-dfs", "fat:riscos-dosfs", "unix:unixfs", …
    family: str  # native representation family, for §4
    representable: Access  # canonical bits this convention can store
    source: str  # citation: BeebWiki table row, spec, …

    def to_canonical(self, native, context: AccessContext) -> Access: ...
    def from_canonical(self, access: Access, context: AccessContext): ...
```

- **Named, because rules are not unique to a pair of systems.** BeebWiki
  lists five DOS↔Acorn mappings (Petrov DOSFS, Sprow DOSFS, LanManFS,
  RISC OS DOSFS, Win95FS) and two for CP/M (CPMFS, ZNOS). A format has a
  default convention and may offer others, selectable where a user needs
  to match a particular tool.
- **Context-aware.** UnixFS derives Owner `x` from Owner R *and* filetype
  `&FE6`, and maps a directory's Locked to NOT world `x`. Directories on
  most Acorn systems carry only `L`. Conventions therefore receive
  `AccessContext`.
- **Owned by the package that owns the format** (`oaknut.dfs` defines
  `acorn-dfs`, and so on), per the no-cross-package-re-export rule. The
  protocol, the canonical word and host conventions live in `oaknut.file`.
- **Registered** on an entry-point axis, like filesystems, so a future
  `oaknut-cpm` or `oaknut-fat` package adds its conventions without
  touching anything else.
- **The single consumer path.** A package's native stat, its
  `write_bytes(access=)` / `chmod`, and its mount's `acorn_meta` /
  `set_acorn_meta` all call its convention. The duck-typed
  `oaknut.file.access_mapping.access_from_stat` and AFS `host_import`'s
  private copy are removed.
- **Tables as data.** Each convention holds its mapping as a small table
  from which both directions, the tests (§6) and the docs table are
  derived.

## 3. The conventions, by family

### Acorn

| Convention | Export (native → canonical) | Import (canonical → native) | Source |
|---|---|---|---|
| `acorn-dfs` | unlocked → `WR` `&03`; locked → `LR` `&09` | keep `L` only: `attr AND &08` | BeebWiki *DFS*; J.G. Harston |
| `adfs` | owner `RWEL` + public `RW(E)`; public E kept once `PE` exists | as stored; directories: `L` (and `R` as ADFS returns) | ADFS formats |
| `afs` | via `AFSAccess.to_acorn` | via `AFSAccess.from_acorn` | AFS0 format |
| `acorn-romfs` | run-only → `E` without `R`; otherwise `R` (proposed — today the adapter exports `&00` for an ordinary file and `Access.X` for run-only) | run-only when `E` set and `R` clear | CFS/ROMFS flag bit 0 |

`acorn-dfs` fixes #57: today's `DFSStat.access` returns `LWR` for a
locked file.

### DOS / FAT (future `oaknut-fat`, DR DOS)

Native attributes: ReadOnly `&01`, Hidden `&02`, System `&04`, Volume
`&08`, Directory `&10`, Archive `&20`. Candidate conventions, straight
from BeebWiki's DOS table:

| Convention | Export formula | Import formula |
|---|---|---|
| `fat:petrov` | `&33 - &22*(RO) + 2*(dosacc AND 4)` | ignore |
| `fat:sprow` | `&0B - &02*(RO) - 8*((dosacc AND 6)=0)` | `1-(acc AND 2)/2 + (acc AND 8)*0.75` |
| `fat:lanmanfs` | `&3B - &22*(RO) - 8*((dosacc AND 6)=0)` | as Sprow |
| `fat:riscos-dosfs` | `&0B - 8*(RO)`, plus System/Hidden/Archive → bits 8–10 | `8-(acc AND 8)/8` |
| `fat:win95fs` | `&3B - 8*(RO)`, plus bits 8–10 | as DOSFS |

The RISC OS conventions are the natural default: they keep System, Hidden
and Archive losslessly in bits 8–10.

### CP/M (future `oaknut-cpm`)

Native attributes: ReadOnly, System, Archive, and the f1–f8 interface
attributes.

| Convention | Export | Import | Source |
|---|---|---|---|
| `cpm:cpmfs` | `&33 - &22*(RO) + 4*(cpmacc AND 2)` (System → `L`) | `1-(acc AND 2)/2 + (acc AND 8)/4` | BeebWiki *CP/M* |
| `cpm:znos` | `&13 - &02*(RO)` | `1-(acc AND 2)/2` | BeebWiki *CP/M* |

CP/M Archive and f1–f8 have no Acorn meaning; they survive only
CP/M→CP/M copies (§4) or through bit 10 for Archive.

### Host

| Convention | Native | Notes |
|---|---|---|
| `unix:unixfs` | POSIX mode bits | BeebWiki *UNIX* (UnixFS). Reading: owner `rw` → Owner `RW`, world `rw` → Public `RW`, directory NOT world `x` → `L`. Writing: Owner `RW` → owner `rw`, Public `RW` → group and world `rw`; file `x` (owner, group) only when the matching R is set and the filetype is `&FE6`; directory owner `x` always, group/world `x` when not Locked |
| `windows:attributes` | `FILE_ATTRIBUTE_*` (ReadOnly, Hidden, System, Archive) | DOS-style, reusing a FAT convention's table; Windows ACLs are out of scope |

Host conventions apply only when oaknut writes or reads real host files
(`get`, `export`, `put`, `import`), and **alongside** INF/xattr sidecars,
never instead of them: the sidecar keeps the full canonical value, while
host permissions give a usable approximation. On Windows, Python sets
only ReadOnly via `os.chmod`; Hidden/System need `SetFileAttributesW`.
Applying host permissions is opt-in or defaulted per platform — an
implementation decision for when it is built.

## 4. Same-family passthrough

Routing a CP/M→CP/M or FAT→FAT copy through the canonical word would
lose attributes Acorn cannot express (f1–f8, Volume). So translation
first compares the source and destination conventions' `family`. When
they match, the native value passes straight through. Only when they
differ does it go native → canonical → native. This is also BeebWiki's
rule for bit 7: keep it only within the same filing system.

## 5. Policy, separate from conventions

Conventions state facts. Choices belong to one shared function in
`oaknut.file`, which every command that moves a file calls:

```python
def translate_access(
    source_native,
    *,
    source: AccessConvention,
    destination: AccessConvention,
    context: AccessContext,
    grant_public: bool = False,  # J.G.'s "as appropriate"
    override: Callable[[Access], Access] | None = None,  # --access, via parse_access_spec
):
    """Native access in the destination's representation."""
```

In order:

1. Same family → pass through (§4).
2. `source.to_canonical`.
3. Drop non-portable bits (bit 7; bits the destination cannot represent).
4. `grant_public`: copy owner `R`/`W` into public where the destination
   has public rights (`&03`→`&33`, `&09`→`&19`). **Default: off.** This
   matches the Level 3 File Server's own default for new files and never
   grants access silently; `WR/WR` would make unlocked files writable by
   every user of a file server. (#57 open question; recommended default.)
5. `override`: the user's `--access` spec (#58), absolute or incremental,
   parsed by the existing `parse_access_spec` so its syntax matches
   `chmod`.
6. `destination.from_canonical`.

Displays (`ls`, `stat`, the `.inf` a `get` writes) always show
`destination.to_canonical(what is stored)`, so they report what the
destination actually holds rather than what was asked for.

## 6. Testing and documentation

- **Table tests per convention**: the BeebWiki rows as test vectors, both
  directions, including directories and the `&FE6` Unix case.
- **Shared property tests over every registered convention**: native →
  canonical → native round-trips unchanged; `to_canonical` never sets bits
  outside `representable`; bit 7 never crosses families.
- **Pinned current behaviour first**: the refactor to conventions lands
  with today's results (including the wrong DFS locked mapping) pinned, so
  behaviour changes arrive as separate, visible commits.
- **Generated docs**: the attribute-mapping table in
  `docs/disc/api/patterns/metadata.rst` is generated from the convention
  tables, so docs and code cannot disagree.

## 7. Delivery order

1. **Conventions layer, pure refactor.** Protocol, registry and the four
   Acorn conventions; every consumer switched to them; duplicates
   removed; current behaviour pinned by tests.
2. **#57** — change the `acorn-dfs` table: locked → `LR`.
3. **#58** — `--access` on `cp` / `put` through `translate_access`.
4. **Canonical word completion** — add `PE`, `PL` and bits 8–10; express
   run-only as `E` without `R`; deprecate then remove `Access.X`. Breaking.
5. **Host conventions** (`unix:unixfs`, `windows:attributes`) when export
   and import start setting host permissions.
6. **FAT / CP/M conventions** with those filing systems.

## Open decisions

- `grant_public` default (recommended: off).
- Retiring `Access.X`, which the ROMFS work deliberately introduced
  (emulator-verified run-only behaviour must be preserved as `E` without
  `R`).
- Default DOS/FAT convention (recommended: `fat:riscos-dosfs`, lossless
  via bits 8–10).
- Whether ZIP (SparkFS) attributes get their own convention.
- Whether host permissions are applied by default, per platform.

## As built (step 1)

Where the implementation differs from the design above, and why:

- **Mounts exchange canonical access.** The `AcornMetadata` capability's
  `acorn_meta` / `set_acorn_meta` carry the canonical word, not native
  values, so a copy between two mounts only ever sees canonical access.
  `translate_access(access, *, destination, context, grant_public,
  override)` therefore takes the source's canonical access and returns
  the canonical access the destination will hold (`destination.settle`),
  rather than a native value. It has no `source` argument.
- **Same-family passthrough (§4) is deferred.** It needs native values to
  cross the mount boundary. For the Acorn families, completing the
  canonical word in step 4 (public E and L) makes same-family copies
  lossless anyway; a native path can be added with the first non-Acorn
  format that needs it.
- **Conventions are found through their mounts.** Each mount advertises
  `access_convention` (optional; the ZIP mount, being read-only, has
  none). An entry-point registry waits for the first convention without
  a mount — the host conventions, or a selectable FAT convention.
- **`from_canonical` takes the current native value** (`current=`), so a
  convention can keep native bits the canonical word cannot express, as
  ADFS keeps directory, public-execute and private.
- **Implemented conventions:** `acorn-dfs` (`oaknut.dfs`), `adfs`
  (`oaknut.adfs`), `afs` (`oaknut.afs`), `acorn-romfs` (`oaknut.romfs`).
  `DFSStat`, `ADFSStat`, `AFSAccess.to_acorn` / `from_acorn`, the write
  paths, `chmod`, AFS host import and every mount use them; the CLI's
  `cp`, `gather`, `import` and `chmod` route through `translate_access`.
- **Run-only as `E` without `R` (step 4, part).** `Access.X` is retired;
  `Access.is_run_only` tests owner `E` without `R`, the `X` access letter
  is rejected with a pointer to `E`, and `format_access_text` shows `E`
  only when the owner has neither `R` nor `W` (BeebWiki `FNf_access`).
  `acorn-romfs` reads an ordinary file as `R` and a run-only one as `E`,
  and writes run-only exactly when the access is run-only. Adding `PE`,
  `PL` and bits 8–10 remains.
- **Behaviour pinned** by `packages/oaknut-disc/tests/test_cli_access_behaviour.py`,
  which records what each copying path produces today, known-wrong rows
  included.

