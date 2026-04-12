# Implementation plan: `oaknut-afs`

Status: **complete** — all 21 phases landed plus follow-up items 1-3, 5-6.
Companion to `docs/afs-proposal.md` — read the proposal first for rationale
and naming. This document is about **what gets built, in what order, with
what public surface**.

## 1. Scope

`oaknut-afs` will provide:

- A **read path** for AFS partitions on old-map ADFS hard-disc images,
  exposed both as a standalone `AFS` handle and as an `afs_partition`
  attribute on an existing `ADFS` handle.
- A **write path**: create / delete / rename / extend / truncate files and
  directories, with quota accounting against the passwords file.
- A **flexible repartitioning** API that takes an old-map ADFS disc and
  carves an AFS region out of its tail. The caller chooses how much space
  to allocate (explicit cylinder/sector/byte count, a ratio, or "as much
  as possible"). When needed, the existing `ADFS.compact()` method
  (already implemented in `oaknut-adfs`) runs first so that a "max"
  request can actually be maximal rather than limited to whatever tail
  free extent happens to exist.
- An **initialisation** API that installs the on-disc structures AFS needs
  to be useful: info blocks, bitmaps, root directory, passwords file, per-
  user root directories, and optional library trees (WFSINIT's full flow).
- A **merge** API that copies a directory subtree from one AFS image into
  another, preserving access/load/exec/date and honouring the target
  user's quota. Used by `initialise()` to lay down libraries, but
  independently useful for any AFS-to-AFS bulk copy.
- A set of **shipped library disc images** (AFS-formatted) committed as
  package resources: `library_model_b` (BBC B/B+), `library_master`
  (Master 128/Compact), `library_archimedes`, and `library_utils`
  (shared). Built once from `econet-fs.tar` by a build script in the
  package's `scripts/` directory.
- A **host-tree import** API (`import_host_tree`) for the other
  direction — pulling a host-side directory or tar (with `host_bridge`
  sidecar metadata) into an AFS image. Primarily used by the library-
  image build script, not by end users.
- A thin CLI surface under the forthcoming `disc` tool for the common
  operations.

Out of scope for v1: new-map ADFS as the host, multi-drive file-server
configurations (where AFS spans several SCSI drives), serving the filesystem
over Econet. See `afs-proposal.md` §5.

## 2. Package layout

```
packages/oaknut-afs/
├── pyproject.toml          # runtime deps: oaknut-file, oaknut-discimage, oaknut-adfs
├── CLAUDE.md               # per-package guidance
├── src/oaknut/afs/         # NB: no src/oaknut/__init__.py
│   ├── __init__.py         # public API re-exports
│   ├── exceptions.py
│   ├── types.py            # SIN, Sector, Cylinder, Geometry, AfsDate
│   ├── access.py           # Access flags, parsing/formatting
│   ├── info_sector.py      # AFS0 info block: parse, build, redundant-copy
│   ├── bitmap.py           # Per-cylinder bitmap + in-memory shadow
│   ├── allocator.py        # MAPMAN-faithful allocator (MBBMCM is the cache manager)
│   ├── map_sector.py       # JesMap: extents, chain traversal, extent stream
│   ├── directory.py        # Linked-list directory read/insert/delete/grow
│   ├── path.py             # AFSPath (pathlib-inspired)
│   ├── passwords.py        # PasswordsFile, UserRecord, StatusByte, BootOption
│   ├── quota.py            # AUTMAN-equivalent credit/debit helpers
│   ├── merge.py            # AFS → AFS subtree copy
│   ├── host_import.py      # host_bridge → AFS tree import (used by build script)
│   ├── afs.py              # AFS class: from_file, context manager, root
│   ├── libraries/          # shipped AFS image assets (binary)
│   │   ├── __init__.py     # LibraryImage enum + importlib.resources loader
│   │   ├── library_model_b.img
│   │   ├── library_master.img
│   │   ├── library_archimedes.img
│   │   └── library_utils.img
│   └── wfsinit/
│       ├── __init__.py     # initialise(), partition entry points
│       ├── partition.py    # AFSSizeSpec, plan(), apply() — flexible sizing
│       ├── layout.py       # InitSpec, UserSpec
│       └── driver.py       # Orchestrates partition → init → library merges
├── scripts/
│   └── build_library_images.py   # one-off: econet-fs.tar → libraries/*.img
└── tests/
    ├── conftest.py         # sys.path shim (see workspace CLAUDE.md)
    ├── helpers/            # AFS-specific test builders
    │   └── afs_image.py    # synthesise minimal valid AFS bytes for fixtures
    ├── test_info_sector.py
    ├── test_bitmap.py
    ├── test_map_sector.py
    ├── test_allocator.py
    ├── test_directory_read.py
    ├── test_directory_write.py
    ├── test_directory_growth.py
    ├── test_path.py
    ├── test_passwords.py
    ├── test_quota.py
    ├── test_afs_read.py
    ├── test_afs_write.py
    ├── test_repartition.py
    ├── test_merge.py
    ├── test_host_import.py
    ├── test_library_images.py
    ├── test_wfsinit_initialise.py
    └── test_byte_exact_wfsinit.py   # compare against a reference WFSINIT image
```

Touches to existing packages:

- `oaknut-adfs`
  - `free_space_map.py`: add `OldFreeSpaceMap.shrink_to(start_cylinder)` and
    `install_afs_pointers(sec1, sec2)` (and the inverse readers).
  - `adfs.py`: add `ADFS.afs_partition -> Optional[AFS]` (lazy, reads the
    `&F6`/`&1F6` words, returns `None` if the map is new-format or the
    pointers are zero). `ADFS.compact()` already exists (`adfs.py:1416`)
    and is used as-is — no new compaction module.
- `oaknut-discimage`
  - No changes expected. `SectorsView` already gives us everything we need.
- Workspace root
  - Add `oaknut-afs` to `[tool.uv.sources]` and to the dev install list.

## 3. Module responsibilities (one-liners)

| Module            | Responsibility                                                            |
|-------------------|---------------------------------------------------------------------------|
| `types`           | Domain newtypes: `SIN`, `Sector`, `Cylinder`, `Geometry`, `AfsDate`       |
| `access`          | `Access` flag set, `from_string("LR/WR")`, `to_string()`, access-byte pack|
| `info_sector`     | `InfoSector` dataclass; `parse(bytes)`, `to_bytes()`; handles redundant copy|
| `bitmap`          | `CylinderBitmap` (one cylinder's sector-0); `BitmapShadow` (all cylinders)|
| `allocator`       | `Allocator.allocate(n)`, `free(sin)`; implements MAPMAN allocation policy (MBBMCM is the cache layer)            |
| `map_sector`      | `MapSector` (JesMap): parse/build, extent list, chain follow; `ExtentStream` giving a `SectorsView`-like concat |
| `directory`       | `AfsDirectory`: iterate, lookup, insert, delete, grow; linked-list walker |
| `path`            | `AFSPath`: navigation, `/`, `read_bytes`, `write_bytes`, `mkdir`, `unlink`|
| `passwords`       | `PasswordsFile`, `UserRecord`, `add`, `remove`, `set_quota`, `set_boot_option`|
| `quota`           | `debit(user, n)`, `credit(user, n)`; raises `AFSQuotaExceededError`       |
| `merge`           | `merge(target, source, source_path, target_path, conflict)` AFS → AFS    |
| `host_import`     | `import_host_tree(target, source, target_path)` via `host_bridge`        |
| `afs`             | `AFS` handle: `from_file`, context manager, `root`, `users`, `flush`     |
| `libraries`       | `LibraryImage` enum + `importlib.resources` loader for shipped assets    |
| `wfsinit.partition` | `AFSSizeSpec`, `plan`, `apply` — flexible sizing + optional compaction |
| `wfsinit.layout`  | `InitSpec`, `UserSpec`                                                   |
| `wfsinit.driver`  | `initialise(adfs, spec)` one-shot — composes partition + init + merges  |

## 4. Public API — reading

```python
from oaknut.afs import AFS, Access

with AFS.from_file("l3fs-master.img") as fs:
    fs.disc_name                      # "Level3MasterDisc"
    fs.geometry                       # Geometry(cylinders=160, heads=4, ...)
    fs.start_cylinder                 # 5
    fs.free_sectors                   # int
    fs.root                           # AFSPath("$")

    for entry in fs.root:             # alphabetical (already sorted on disc)
        print(entry.name, entry.access, entry.length, entry.sin)
        if entry.is_directory:
            ...

    data = (fs.root / "Library" / "Fs").read_bytes()
    stat = (fs.root / "Library" / "Fs").stat()  # AFSStat(length, access, date, load, exec)

    # Read-only users view is always available
    for user in fs.users:
        print(user.name, user.free_space, user.is_system, user.boot_option)
```

`AFS.from_file` opens the disc read-only by default. Passing `writable=True`
selects the write path (§5). The context manager writes any pending changes
on successful `__exit__`; an explicit `fs.flush()` is also exposed.

When the image is *already* an ADFS disc and we want to reach AFS through
it, the natural entry point is:

```python
from oaknut.adfs import ADFS

with ADFS.from_file("l3fs-master.img") as adfs:
    afs = adfs.afs_partition          # Optional[AFS]
    if afs is not None:
        ...                           # same surface as above
```

`adfs.afs_partition` is lazy and does not open a second file handle — it
shares the underlying `UnifiedDisc`.

## 5. Public API — writing

Opened writable, every mutating call goes through the allocator, directory
layer, and quota accountant in that order, and flushes are deferred until
context exit or explicit flush.

```python
from oaknut.afs import AFS, Access, BootOption

with AFS.from_file("disc.img", writable=True, user="Syst") as fs:
    (fs.root / "Docs").mkdir()                           # DIRMAN insert + allocate dir
    (fs.root / "Docs" / "README").write_bytes(
        b"...",
        load=0x0000FFFF,
        exec_=0x0000FFFF,
        access=Access.from_string("LR/R"),
    )
    (fs.root / "Obsolete").unlink()                      # file or empty dir
    (fs.root / "Docs" / "README").rename(fs.root / "Docs" / "Readme")

    # passwords admin (requires system privilege on the acting user)
    fs.users.add("alice", password="secret", quota=0x40000000)
    fs.users.set_quota("alice", 0x80000000)
    fs.users.set_boot_option("alice", BootOption.RUN)
    fs.users.remove("bob")
```

Key decisions baked into this surface:

- **Single "acting user"** per session, supplied at `from_file` time.
  Defaults to `"Syst"`. Quota debits/credits and access checks are made on
  this user. We do **not** model multi-user concurrent sessions.
- **Atomicity.** Mutations buffer into the `SectorsView` layer. On a clean
  context exit they flush; on an exception they are discarded (the
  underlying disc image is not modified). This gives all-or-nothing
  semantics for, say, `initialise()`.
- **Quota enforcement** is real by default. Tests that want to bypass it
  pass `enforce_quota=False` to `from_file`. The `Syst` user is *not* an
  exception: the PDF is explicit that system users are subject to normal
  quota rules.
- **Rename** is handled entirely in the directory layer (rewrite name
  in-place, bump `master_seq`); no reallocation is required when the
  target is in the same directory. Cross-directory rename is an insert +
  delete.

## 6. Public API — repartitioning

Partitioning is factored into a **plan** (pure, returns a dataclass) and an
**apply** (mutates the disc). This is the same shape as `git merge
--no-commit` and makes dry-runs trivial to test. The caller chooses how
much space to allocate via an `AFSSizeSpec` algebraic type, and may opt
into (or out of) running `ADFS.compact()` as a preparatory step.

```python
from oaknut.adfs import ADFS
from oaknut.afs.wfsinit import partition, AFSSizeSpec

with ADFS.from_file("disc.img", writable=True) as adfs:
    plan = partition.plan(
        adfs,
        size=AFSSizeSpec.max(),     # largest AFS region the disc can hold
                                     # after compaction (the common case)
        compact_adfs=True,           # False → use only current tail free
    )
    print(plan)
    # RepartitionPlan(
    #     start_cylinder=5,
    #     afs_cylinders=155,
    #     new_adfs_cylinders=5,
    #     sec1=0x51, sec2=0x61,
    #     total_afs_sectors=2480,
    #     will_compact=True,         # apply() must run adfs.compact() first
    # )

    partition.apply(adfs, plan)      # adfs.compact() (if will_compact)
                                      # then shrink ADFS + install pointers
```

`AFSSizeSpec` is a small algebraic type with constructors:

- `AFSSizeSpec.max()` — the largest AFS region the disc can hold after
  compaction (if enabled). The common "just do the right thing" case.
- `AFSSizeSpec.cylinders(n)` / `sectors(n)` / `bytes(n)` — explicit size;
  rounded up to a cylinder boundary (AFS partitions always start on a
  cylinder boundary).
- `AFSSizeSpec.ratio(afs, adfs)` — split the remaining space in the given
  ratio. E.g. `.ratio(afs=2, adfs=1)` gives AFS two-thirds of the
  available cylinders.
- `AFSSizeSpec.existing_free()` — WFSINIT's historical behaviour: use
  exactly the current tail free extent, no compaction, fail if the free
  list is fragmented.

**Computing the plan without running compaction.** Since `ADFS.compact()`
always produces a single tail free extent containing `total_sectors −
used_sectors` sectors, the post-compaction layout is mathematically
derivable from the current free-space map: `used_sectors = total_sectors
− sum(free_lengths)`. `partition.plan()` uses this to report the
resulting start cylinder as a dry-run without touching any bytes.
`partition.apply()` then calls `adfs.compact()` first (iff
`plan.will_compact` is true), re-reads the free-space map, and runs
`OldFreeSpaceMap.shrink_to(start_cylinder)` +
`install_afs_pointers(sec1, sec2)`.

`partition.plan` refuses (raises `AFSRepartitionError` with a specific
subclass) if:

- the ADFS map is new-format (`AFSNewMapNotSupportedError`);
- the disc already contains AFS pointers (`AFSAlreadyPartitionedError`);
- the requested size would leave fewer than the WFSINIT minimum cylinders
  for ADFS after shrinking (`AFSInsufficientADFSSpaceError`);
- `compact_adfs=False` and the ADFS free list is fragmented
  (`AFSDiscNotCompactedError`).

`partition.apply` is one transaction — if any step fails, the disc is
untouched. On success it leaves the AFS region with *no* AFS structures
yet, just a shrunken ADFS map with pointers. The next step is
`initialise()`.

## 7. Public API — initialisation

`initialise()` is the Python analogue of WFSINIT's full flow: partition
the disc, write the bitmaps, write the two info blocks, create the root
directory, create the passwords file with its users, create per-user
URDs, and optionally merge in shipped library disc images.

```python
import datetime

from oaknut.adfs import ADFS
from oaknut.afs import BootOption, LibraryImage
from oaknut.afs.wfsinit import initialise, InitSpec, UserSpec, AFSSizeSpec

with ADFS.from_file("blank-l-disc.img", writable=True) as adfs:
    initialise(
        adfs,
        spec=InitSpec(
            disc_name="Level3MasterDisc",
            date=datetime.date(2026, 4, 11),
            size=AFSSizeSpec.max(),
            addition_factor=0,
            default_quota=0x40404,           # WFSINIT's original default
            users=[
                UserSpec("Syst", password="", system=True, boot=BootOption.RUN),
                UserSpec("BeebMaster"),
                UserSpec("Games"),
            ],
            libraries=[
                LibraryImage.UTILS,
                LibraryImage.MODEL_B,
                LibraryImage.MASTER,
            ],
        ),
    )
```

Types:

```python
@dataclass(frozen=True)
class UserSpec:
    name: str
    password: str = ""
    quota: int | None = None           # None → use InitSpec.default_quota
    system: bool = False
    privileged: bool = False
    boot: BootOption = BootOption.OFF

@dataclass(frozen=True)
class InitSpec:
    disc_name: str                     # ≤16 chars, printable ASCII
    date: datetime.date
    size: AFSSizeSpec = field(default_factory=AFSSizeSpec.max)
    compact_adfs: bool = True
    addition_factor: int = 0           # multi-drive; 0 for single-drive
    default_quota: int = 0x40404       # WFSINIT's original; tune up for
                                        # large modern images
    users: Sequence[UserSpec] = ()
    libraries: Sequence[LibraryImage] = ()  # shipped images to merge in
    repartition: bool = True           # False → assume partition.apply already ran
```

Validation is done up-front in `InitSpec.__post_init__`: disc name length
and charset, date range, unique user names, name charset (letter first,
alnum/`!`/`-`, ≤10 chars). A bad spec raises before any bytes are written.

`initialise()` is one transaction. It opens the AFS region writable,
stages all of the writes in memory, and flushes once on success. An
exception anywhere in the flow leaves the disc untouched. If
`spec.repartition=False` the disc is assumed to have been through
`partition.apply` already; this mode is useful for tests and for
integrating with hand-crafted layouts.

The deliberate deviations from WFSINIT (see proposal §3) apply: phantom
entry bug fixed, no BASIC memory leak. The default quota however is
**kept at WFSINIT's original `0x40404`** (~256 KiB, per `WFSINIT.bas:4890`)
because the L3FS address encoding caps a single drive at ~512 MB, and
real-period Winchesters were ~20 MB. Callers building discs for modern
large images can raise `InitSpec.default_quota` explicitly.

## 8. Public API — merge (AFS → AFS)

`merge()` copies a directory subtree from one AFS image into another,
preserving access / load / exec / date and debiting the target user's
quota.

```python
from oaknut.afs import AFS, merge

with AFS.from_file("target.img", writable=True, user="Syst") as target:
    with AFS.from_file("library.img") as source:
        merge(
            target,
            source,
            source_path=source.root,            # subtree to copy
            target_path=target.root / "Library",
            conflict="error",                   # "error" | "skip" | "overwrite"
        )
```

The merge walks the source tree recursively and recreates each directory
and file in the target through the write path. On `conflict="error"`, a
name clash raises `AFSMergeConflictError` before any bytes are written —
the merge is dry-run-walked first to collect conflicts. `"skip"` leaves
existing target entries alone; `"overwrite"` replaces them (and
re-debits the quota for the new version, crediting back the replaced
bytes).

This is the mechanism `initialise()` uses to place the shipped library
images. It is also usable directly by end-user code for any AFS-to-AFS
bulk copy, which means library updates, migrations between discs, and
test-fixture construction all share one implementation.

## 8a. Public API — shipped library images

Four AFS disc images ship as package resources under
`src/oaknut/afs/libraries/` and are exposed via a `LibraryImage` enum:

```python
class LibraryImage(Enum):
    UTILS      = "library_utils.img"      # Utils (shared)
    MODEL_B    = "library_model_b.img"    # "Library" — BBC B / B+ (ANFS)
    MASTER     = "library_master.img"     # "Library1" — Master 128/Compact
    ARCHIMEDES = "library_archimedes.img" # "ArthurLib" — Archimedes

    @classmethod
    def ALL(cls) -> list[LibraryImage]:
        return list(cls)

    def open(self) -> AFS:
        """Open the image read-only via importlib.resources."""
        ...
```

The images are built once from `econet-fs.tar` by
`scripts/build_library_images.py`, which uses `import_host_tree()` to
pull each source directory into a fresh AFS image and writes the result
under `src/oaknut/afs/libraries/`. The resulting `.img` files are
committed as binary assets and serve as runtime resources for
`initialise()` and as regression fixtures for tests.

## 8b. Public API — host-tree import

The other direction of bulk movement: pull a host-side directory or tar
into an AFS image via `oaknut.file.host_bridge`.

```python
from pathlib import Path

from oaknut.afs import AFS, import_host_tree

with AFS.from_file("new.img", writable=True, user="Syst") as target:
    import_host_tree(
        target,
        source=Path("library/econet-fs/Library"),
        target_path=target.root / "Library",
    )
```

xattrs / sidecars on the host side are honoured for access / load /
exec via the existing `MetaFormat` negotiation; files without metadata
get sensible AFS defaults.

This is primarily how the shipped library images are *created*. It is
exposed as public API for ad-hoc bulk imports and for users building
custom library images, but it is **not** the recommended path for
populating a freshly-initialised disc — use `initialise(...,
libraries=[...])` or `merge()` from a prepared image instead, so that
users benefit from golden reference data rather than rebuilding from
a local directory every time.

## 9. Public API — passwords and quotas

`fs.users` is a `PasswordsFile` view. Read-only on a read-only session;
mutable on a writable session opened by a system user.

```python
for user in fs.users:
    user.name              # "BeebMaster"
    user.group             # Optional[str] — the "group." prefix form
    user.free_space        # int, bytes
    user.is_in_use
    user.is_system
    user.is_privileged
    user.boot_option       # BootOption.{OFF, LOAD, RUN, EXEC}

fs.users["BeebMaster"]     # UserRecord, by name lookup

fs.users.add("alice", password="secret", quota=0x40404)
fs.users.remove("alice")
fs.users.set_quota("alice", 0x100000)
fs.users.set_password("alice", "newsecret")
fs.users.set_boot_option("alice", BootOption.RUN)
fs.users.grant_system("alice")
fs.users.revoke_system("alice")
```

All mutating operations check that the **acting user** of the session has
system privilege, per the PDF's "principles of object access" section.
`AFSAccessDeniedError` is raised otherwise.

Quota debit/credit is *not* part of the public API — it is driven
internally by file create/extend/delete. Tests can observe the resulting
`user.free_space` values via the read surface and assert the invariant
`sum(user.free_space for u in users) + used_bytes == capacity`.

## 10. Error hierarchy

```
AFSError                           base
├── AFSFormatError                 malformed on-disc structure
│   ├── AFSBrokenDirectoryError    master-seq mismatch (FS Error 42)
│   ├── AFSBrokenMapError          JesMap magic or seq mismatch
│   └── AFSInfoSectorError         AFS0 magic or redundancy mismatch
├── AFSPathError                   path syntax or non-existent object
├── AFSAccessDeniedError           acting user lacks permission
├── AFSFileLockedError             L bit set, op disallowed
├── AFSInsufficientSpaceError      allocator cannot satisfy request
├── AFSQuotaExceededError          AUTMAN-equivalent refusal
├── AFSRepartitionError            base for repartition failures
│   ├── AFSNewMapNotSupportedError
│   ├── AFSDiscNotCompactedError   (only when compact_adfs=False)
│   ├── AFSAlreadyPartitionedError
│   └── AFSInsufficientADFSSpaceError
├── AFSMergeConflictError          AFS → AFS merge name clash
└── AFSHostImportError             host_bridge import failed
```

Where the server has a numeric FS error code (e.g. 42 for Broken
Directory), the exception carries it as `err.fs_error_code` for symmetry
with the server's own error reporting.

## 11. Testing strategy

Four concentric test rings, from innermost to outermost:

### a) Hand-crafted byte fixtures

Each structure module has tests that build tiny synthetic bytes, parse
them, and assert field-by-field decoding; and vice versa (build from a
dataclass, compare bytes). These tests do not touch `UnifiedDisc` and do
not require any image file. They are the fastest and flush out the vast
majority of off-by-one / endianness / packing bugs.

### b) Beebmaster PDF transcription fixture

The PDF contains worked hex dumps of a specific test disc's info sector,
root directory, passwords file, and a JesMap. Transcribe those into a
Python constant (`tests/fixtures/beebmaster_test_disc.py`), build a
minimal AFS image around them in-memory, and assert that our read path
reports exactly the field values the PDF says it should. This is our
golden-file regression check for the read path.

### c) Round-trip tests

For every write operation, a test that:

1. Initialises a small AFS image in memory via `initialise()`.
2. Performs the write operation.
3. Closes and re-opens the image.
4. Reads back and asserts the resulting state.

Round-trip tests also assert the quota invariant
`sum(user.free_space) + used == capacity` on every mutation.

### d) Byte-exact WFSINIT comparison

We cut a real AFS reference image once — either by running the original
WFSINIT in a BBC Micro emulator or by using an existing disc image we
already trust — and commit it under `tests/data/images/` per
`feedback_test_data_in_git`. `test_byte_exact_wfsinit.py` drives our
`initialise()` with the same spec WFSINIT was given and asserts **byte
equality** against the reference image for the AFS region. Deviations we
deliberately made (quota default, phantom-entry fix) are captured by
running that test in a "WFSINIT-compatibility mode" where `initialise()`
reproduces the buggy behaviour. This compatibility flag is not part of
the public API.

### e) Cross-checks from L3V126 ROM reading

As `docs/afs-onwire.md` grows, every non-obvious fact extracted from the
ROM becomes a unit test. Example: if DIRMAN turns out to grow directories
by doubling, `test_directory_growth.py` has a test that inserts until the
directory grows and asserts the new size is 2× the old.

## 12. Phased delivery

Phases are small enough that each ends at a commit-worthy boundary with
green tests. Each phase names the L3V126 modules it depends on (if any),
the tests that must pass to declare it done, and the external artifacts
produced.

### Phase 0 — Research and spec bootstrap
- **Inputs:** L3V126 `Uade01`, `Uade02`.
- **Output:** `docs/afs-onwire.md` seeded with authoritative struct
  layouts cited to `Uade0x.asm:<label>`.
- **Done when:** every field referenced in the proposal and in this plan
  has a citation in `afs-onwire.md`.

### Phase 1 — Package scaffold
- New workspace member `oaknut-afs`, empty modules with docstrings and
  imports, `CLAUDE.md`, `pyproject.toml`, bumpversion config, namespaced
  tag format. Namespace-init guard still green.
- `types.py`, `access.py`, `exceptions.py` land populated.
- **Tests:** `test_access.py` (string ↔ byte round-trip for every entry in
  the PDF's access table).

### Phase 2 — Info sector
- **Inputs:** WFSINIT md §6, PDF pp.5-6.
- `info_sector.py` full. Redundant-copy verification.
- **Tests:** `test_info_sector.py` — beebmaster PDF fixture parses to the
  exact field values in the PDF; round-trip serialises back to the same
  bytes.

### Phase 3 — Bitmap layer
- `bitmap.py`: `CylinderBitmap` (one cylinder) and `BitmapShadow` (all
  cylinders with per-cylinder free count, cached). Read + write.
- **Tests:** `test_bitmap.py` — free/allocate/free invariants, byte
  ordering matches PDF example.

### Phase 4 — Map sector, single-chain
- **Inputs:** PDF pp.7-8.
- `map_sector.py`: parse, build, iterate extents, compute length, reject
  on seq mismatch.
- `ExtentStream` wrapping a list of extents and exposing a `SectorsView`-
  like indexable stream over them.
- **Tests:** `test_map_sector.py` — PDF JesMap fixture; multi-extent
  synthetic fixtures.

### Phase 5 — Directory read (static ≤19 entries)
- `directory.py`: header parse, linked-list walk, `__iter__`, `__getitem__`.
- `path.py`: `AFSPath`, `/`, `name`, `parts`, traversal.
- **Tests:** `test_directory_read.py` + `test_path.py` — the root
  directory from the beebmaster PDF fixture parses to the exact object
  list the PDF shows.

### Phase 6 — `AFS` class, ADFS integration, end-to-end read
- `afs.py`: `AFS.from_file`, context manager, `.root`, `.disc_name`,
  `.geometry`, `.start_cylinder`, `.free_sectors`.
- `ADFS.afs_partition` in `oaknut-adfs`.
- `passwords.py` read-only side.
- **Tests:** `test_afs_read.py` walks a full AFS image and reads file
  bytes; `test_repartition_roundtrip.py` opens an ADFS+AFS disc through
  the ADFS handle and reaches AFS.
- **Milestone:** end-to-end read path shippable.

### Phase 7 — Map chaining & directory growth (read side)
- **Inputs:** L3V126 **MAPMAN** (`Uade10`–`Uade13`), **DIRMAN**
  (`Uade0C`–`Uade0E`).
- Extend `map_sector.py` to follow multi-sector map chains.
- Extend `directory.py` to read directories above 19 entries regardless
  of how the server grows them.
- `afs-onwire.md` updated with what was found.
- **Tests:** synthetic fixtures for a 3-extent chained-map file and a
  50-entry directory.

### Phase 8 — Allocator
- **Inputs:** L3V126 **MAPMAN** (`Uade10`–`Uade13`). Note: the original
  plan cited **MBBMCM** as the allocator, but ROM reading revealed that
  MBBMCM is the bit-map / map-block **cache manager**. The allocation
  *policy* (cylinder selection via FNDCY, first-fit bitmap scan via
  ALBLK, cross-cylinder spill via FLBLKS, deallocation via
  DAGRP/CLRBLK) lives in MAPMAN.
- `allocator.py`: `allocate(n_sectors)` returns a list of extents plus
  the chosen map sector SIN; `free(sin)` walks the map and releases.
- Policy matches MAPMAN where it matters for byte equality with WFSINIT
  output.
- **Tests:** `test_allocator.py` — free space accounting invariants,
  contiguous and fragmented allocation, spill across cylinders.

### Phase 9 — Directory write, no growth
- `directory.py` insert/delete/rename for directories that fit in their
  current allocation. Master-sequence bump + tail copy.
- **Tests:** insert in sorted position, delete re-splicing, rename
  in-place; every assertion cross-checked by re-parsing the mutated
  bytes.

### Phase 10 — Directory growth
- **Inputs:** DIRMAN findings from phase 7.
- Implement whichever growth strategy the ROM uses.
- **Tests:** `test_directory_growth.py` inserts until growth triggers,
  asserts the new allocation is valid and all prior entries survived.

### Phase 11 — File create / write
- `path.write_bytes()` with load/exec/access. Wires through allocator,
  JesMap build, directory insert, quota debit.
- **Tests:** `test_afs_write.py` create-and-read-back; quota invariant.

### Phase 12 — File extend / truncate
- **Inputs:** L3V126 **RNDMAN** (`Rman01`–`Rman05`) + MAPMAN.
- `path.write_bytes()` to an existing file, and an explicit
  `path.truncate(length)`. Handles in-place extent extension vs new
  extent append vs chained-map-sector append.
- **Tests:** every transition between extent configurations, plus quota
  debit/credit on each.

### Phase 13 — File / directory delete
- `path.unlink()` and `path.rmdir()`; empty-dir check, locked-file
  refusal, quota credit.
- **Tests:** delete round-trip, locked-file refusal, non-empty-dir
  refusal.

### Phase 14 — Passwords write + quota admin
- **Inputs:** L3V126 **AUTMAN** (`Uade0F`) + **USRMAN** (`Uade06`).
- `PasswordsFile` mutation: `add`, `remove`, `set_quota`, `set_password`,
  `set_boot_option`, `grant_system`, `revoke_system`.
- Acting-user permission checks on every mutation.
- **Tests:** `test_passwords.py` round-trip every operation; assert
  that a non-system acting user cannot mutate.

### Phase 15 — `wfsinit.partition` (flexible sizing)
- `wfsinit/partition.py`: `AFSSizeSpec`, `RepartitionPlan`, `plan()`,
  `apply()`. `apply()` calls `adfs.compact()` first when `will_compact`.
- `OldFreeSpaceMap.shrink_to` + `install_afs_pointers` in `oaknut-adfs`.
- **Tests:** `test_repartition.py` — each `AFSSizeSpec` constructor
  against a clean disc; a fragmented disc round-trip that exercises
  compaction; refusal for every error mode in §6; reopen as ADFS and
  assert the new `&FC` size and `&F6`/`&1F6` pointers match the plan.

### Phase 16 — AFS → AFS merge
- `merge.py`: `merge(target, source, source_path, target_path, conflict)`.
  Walks source subtree, recreates each directory/file in the target via
  the write path, preserving access/load/exec/date, debiting the target
  user's quota. Two-pass with a dry-run conflict-gather phase when
  `conflict="error"`.
- **Tests:** `test_merge.py` with synthetic source+target AFS images:
  preserve-metadata round-trip, each `conflict` policy, quota debit.

### Phase 17 — Host-tree import
- `host_import.py`: `import_host_tree(target, source, target_path)`,
  wiring through `oaknut.file.host_bridge`.
- **Tests:** `test_host_import.py` — tiny on-disk source tree with
  sidecars imports into a fresh AFS image, metadata preserved.

### Phase 18 — Shipped library images
- `scripts/build_library_images.py` reads `econet-fs.tar` and uses phase
  17 to produce four AFS images under `src/oaknut/afs/libraries/`.
- `libraries/__init__.py` with the `LibraryImage` enum and
  `importlib.resources` loader.
- Commit the four `.img` files as binary assets.
- **Tests:** `test_library_images.py` — each committed `.img` opens and
  contains the expected directory tree.

### Phase 19 — `wfsinit.initialise`
- `wfsinit/driver.py`: orchestrates partition → info blocks → bitmaps →
  root dir → passwords → per-user URDs → library merges (via phase 16),
  all inside one transaction.
- `InitSpec` / `UserSpec` validation in `__post_init__`.
- **Tests:** `test_wfsinit_initialise.py` — initialise a blank ADFS disc
  with chosen libraries, reopen as AFS, assert disc name, user list,
  URDs, quotas, library trees.

### Phase 20 — Byte-exact WFSINIT compatibility mode
- Private test-only `wfsinit_compat=True` that reproduces the quirks
  (phantom-entry bug, specific allocation ordering) required to match a
  reference WFSINIT image byte-for-byte.
- **Tests:** `test_byte_exact_wfsinit.py` against a committed reference
  image in `tests/data/images/`.

### Phase 21 — `disc afs` CLI
- Sub-commands: `disc afs init`, `disc afs ls`, `disc afs cat`,
  `disc afs put`, `disc afs users`. Plus `disc adfs compact` for the
  existing ADFS compaction operation.
- Follows the `cli-design.md` conventions.
- **Tests:** `test_cli.py` — golden-output tests on a fixture image.

## 13. Cross-cutting concerns

### Transactional writes

The `AFS` class owns an in-memory write buffer layered over its
`SectorsView`. All mutating operations write into that buffer. On
successful `__exit__` the buffer is flushed to the underlying disc image
in one pass; on exception it is dropped. `flush()` is exposed for long-
running sessions. This gives `initialise()` all-or-nothing semantics for
free and, crucially, means a botched phase 16 test cannot corrupt a
reference image on disc.

### Byte-exact mode vs sensible defaults

Two modes are distinguished explicitly:

- **Default mode** (`wfsinit_compat=False`): sensible defaults, bugs
  fixed, quota set to `default_quota`. This is what end users want.
- **Compat mode** (`wfsinit_compat=True`): reproduces WFSINIT quirks for
  the phase-18 byte-equality test. Not a public API feature — it is
  reachable from tests via a private module symbol, not via `InitSpec`.

### PEP 420 discipline

Every new file lives under `src/oaknut/afs/<name>.py`. There is **no**
`packages/oaknut-afs/src/oaknut/__init__.py`. The existing
`scripts/check_no_namespace_init.sh` pre-commit hook protects this; the
per-package `CLAUDE.md` calls it out again for emphasis.

### Naming conventions

`_filename`, `_filepath`, `_dirpath`, `_dirname` throughout, per workspace
convention. "disc" in prose, never "disk".

### Test-first

Every phase above lists its tests before its code. New structures get a
hand-crafted byte fixture test before they acquire any logic. Bugs that
escape to `test_afs_read.py` or later are a signal that an earlier
phase's unit coverage was too thin; the fix is a regression test at the
lowest layer that would have caught it, not a patch in the end-to-end
test.

## 14. Risks and mitigations

| Risk                                                   | Mitigation                                                       |
|--------------------------------------------------------|------------------------------------------------------------------|
| Directory growth strategy in DIRMAN is subtler than expected | Phase 7 reads DIRMAN *before* any write code ships; growth tests in phase 10 |
| MAPMAN allocator heuristic is hard to match byte-exact (MBBMCM is just the cache layer) | Split the test into "correctness" (phase 8) and "byte-exact" (phase 20); the former ships independently |
| Quota accounting drift on edge cases                   | Invariant assertion on every mutation in every round-trip test   |
| Reference WFSINIT image unavailable                    | Phase 20 is optional for v1 shipping; phases 1–19 stand alone    |
| New-map ADFS disc encountered in the wild              | `partition.plan` raises `AFSNewMapNotSupportedError` early; revisit only if demand appears |
| `import_host_tree` over-claims about xattr round-trip  | Test `test_host_import.py` asserts which attributes survive; those that don't are documented as lost-on-import, not silently dropped |
| Shipped library images drift vs `econet-fs.tar` source | Build script is reproducible and deterministic; a test rebuilds an image in-memory and compares against the committed asset to detect drift |

## 15. Open points for review

These are the decisions this plan has made that I'd like explicit sign-off
on before coding starts:

1. **Package name `oaknut-afs` / module `oaknut.afs`.** Confirmed in
   `afs-proposal.md`, mentioned here for completeness.
2. **Acting-user model.** One acting user per session, supplied at
   `from_file`, no concurrent multi-user. Simpler than the server, which
   we are not trying to be.
3. **Transactional flush on context exit** vs write-through. I've chosen
   transactional; the alternative is simpler but loses all-or-nothing
   semantics for `initialise()`.
4. **Default quota `0x40404`** (~256 KiB), matching WFSINIT's original
   at `WFSINIT.bas:4890`. The L3FS SCSI address encoding caps a single
   drive at ~512 MB (21-bit sector address × 256-byte sectors), and
   real-period L3FS Winchesters were ~20 MB, so a quota measured in
   gigabytes would be larger than any disc this filesystem can
   physically address. `InitSpec.default_quota` remains tunable, so
   callers building discs on modern large images can raise it.
5. **`wfsinit_compat` mode** is a private test-only knob, not part of the
   public API.
6. **Library packaging as shipped AFS images** rather than a
   `LibraryLayout` enum over a generic host_bridge source tree. Four
   images — `library_model_b`, `library_master`, `library_archimedes`,
   `library_utils` — all built once from `econet-fs.tar` by
   `scripts/build_library_images.py` and committed under
   `src/oaknut/afs/libraries/`. Utils is a fourth shared image (not
   bundled into each machine-specific image) to let callers mix and
   match.
7. **ADFS as a hard runtime dependency** of `oaknut-afs`. The alternative
   — lazy import of `oaknut-adfs` only inside `partition.py` — is a
   micro-optimisation not worth the complexity.

If any of these need to change, the knock-on edits are bounded and live
in this document, not in code.
