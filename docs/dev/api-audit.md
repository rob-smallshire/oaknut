# API audit — oaknut public surface

Walking the API cookbook recipes against the live code surfaced a
mix of missing affordances, gratuitous inconsistencies between
sibling packages, and ergonomic regressions where one filesystem
got a friendlier helper than the others. This document lists every
finding, with a proposed fix, so the API-side work can be sequenced
before we touch the cookbook.

Themes are ordered roughly by impact-per-line, not implementation
size. Each theme calls out which package(s) it touches.

| Theme | GitHub issue |
|---|---|
| 1 + 2: symmetric export_file / import_file | [#23](https://github.com/rob-smallshire/oaknut/issues/23) |
| 3: drop copy_file target_fs | [#24](https://github.com/rob-smallshire/oaknut/issues/24) |
| 4: unify write_bytes access surface | [#25](https://github.com/rob-smallshire/oaknut/issues/25) |
| 5: unified Stat protocol | [#26](https://github.com/rob-smallshire/oaknut/issues/26) |
| 6: dfs.root should be `$` | [#27](https://github.com/rob-smallshire/oaknut/issues/27) — **closed as won't-fix**, see correction at the end of theme 6 below |
| 7: DFS.from_file format auto-detect | [#28](https://github.com/rob-smallshire/oaknut/issues/28) |
| 8: AFS.create_file orchestrator | [#29](https://github.com/rob-smallshire/oaknut/issues/29) |
| 9: capacity strings on create_file / UserSpec | [#30](https://github.com/rob-smallshire/oaknut/issues/30) |
| 10: AFS top-level re-exports | [#31](https://github.com/rob-smallshire/oaknut/issues/31) |
| 11: AcornMeta field rename | [#32](https://github.com/rob-smallshire/oaknut/issues/32) |

---

## 1. `entry.export_file()` exists but the cookbook still marshals by hand

**Where**: `oaknut.dfs.DFSPath.export_file` (`dfs/dfs.py:351`),
`oaknut.adfs.ADFSPath.export_file` (`adfs/adfs.py:785`).
**Missing on**: `oaknut.afs.AFSPath` — no `export_file` method at all.

The cookbook recipe "Exporting with metadata sidecars" predates these
methods and still does the disassemble/reassemble dance:

```python
data = entry.read_bytes()
st = entry.stat()
meta = AcornMeta(load_addr=st.load_address, exec_addr=st.exec_address, attr=int(st.access))
export_with_metadata(data, Path("output") / entry.name, meta, meta_format=MetaFormat.INF_TRAD)
```

When all the input is `entry`, the right shape is:

```python
entry.export_file(Path("output") / entry.name, meta_format=MetaFormat.INF_TRAD)
```

**Proposed fix**

- Add `AFSPath.export_file(target_filepath, *, meta_format=..., owner=0)` mirroring the DFS/ADFS implementation.
- Update the cookbook to use the method form everywhere.
- Mark `oaknut.file.export_with_metadata` as the low-level primitive — keep it, but make `export_file` the documented public path.

## 2. `import_file` is only on ADFS

**Where**: `oaknut.adfs.ADFSPath.import_file` (`adfs/adfs.py:821`).
**Missing on**: DFSPath, AFSPath.

Symmetric to `export_file`: a user with a host file + sidecar should be able to write into any image, not only ADFS. Without it, the cookbook would have to teach manual `host_bridge` plumbing the moment we add an import-side recipe.

**Proposed fix**: add `DFSPath.import_file` and `AFSPath.import_file` with the same signature as `ADFSPath.import_file`.

## 3. `copy_file`'s `target_fs` argument duplicates information already in `dst`

**Where**: `oaknut.file.copy.copy_file` (`file/copy.py:22`).

```python
copy_file(src, dst, target_fs="adfs")
```

`dst` already knows what filesystem it lives on — it is an `ADFSPath` or `DFSPath` or `AFSPath`. The string `target_fs` is the user being asked to repeat that fact so `access_to_write_kwargs` can dispatch.

**Proposed fix**

- Each path class exposes an internal `_target_fs_kind` constant (`"dfs"` / `"adfs"` / `"afs"`), or — better — a polymorphic `_apply_access(stat) -> dict` method.
- `copy_file(src, dst)` becomes single-argument-pair: source and destination are sufficient.
- Bonus: surface the symmetric method-form `src.copy_to(dst)` for readability.

## 4. `write_bytes` access surface differs across filesystems

**Where**:
- `DFSPath.write_bytes(data, *, load_address, exec_address, locked)` — bool
- `ADFSPath.write_bytes(data, *, load_address, exec_address, locked)` — bool
- `AFSPath.write_bytes(data, *, load_address, exec_address, access, date)` — Access object + date

The DFS/ADFS shape is a thin lie: ADFS actually has full per-owner/per-public RWE access; the `locked: bool` shortcut just sets a single bit. AFS exposes the full access type honestly, plus a date.

**Proposed fix**

- Unify on `access: Access | bool | None = None` across all three.
- `True` / `False` still works for the locked-only shorthand readers expect.
- An `Access` object expresses the full bit pattern where the filesystem can store it.
- Add an optional `date: AfsDate | None = None` to DFS/ADFS too — silently ignored when the format has no date field, used when it does (ADFS stamps directories with dates).

## 5. `stat()` return type is three different shapes

**Where**:
- `DFSPath.stat() -> DFSStat`: `length, load_address, exec_address, locked, start_sector, is_directory`
- `ADFSPath.stat() -> ADFSStat`: `length, load_address, exec_address, locked, owner_read, owner_write, owner_execute, public_read, public_write, public_execute, is_directory`
- `AFSPath.stat() -> DirectoryEntry`: `name, load_address, exec_address, access, date, sin` — no `length`, no `is_directory`

A user iterating across filesystems cannot write polymorphic code: `st.is_directory` works on DFS/ADFS but not AFS, `st.length` works on DFS/ADFS but not AFS, `st.access` works on AFS but DFS/ADFS forces them to assemble it from `locked` + the bool RWE fields.

**Proposed fix**

- Define a `Stat` protocol (in `oaknut-file`) with at minimum: `length: int`, `load_address: int`, `exec_address: int`, `access: Access`, `is_directory: bool`, `date: AfsDate | None`.
- DFSStat / ADFSStat / AFSStat all conform.
- AFS's `stat()` should return an `AFSStat` (synthesised from the `DirectoryEntry` + the size from the map chain), not a raw `DirectoryEntry`. The `DirectoryEntry` stays available as a lower-level accessor for callers who need its `sin` field.

## 6. DFS root is `""`, ADFS root is `"$"` — joining looks different

**Where**: `DFS.root` returns `DFSPath(self, "")` (`dfs/dfs.py:758`); `ADFS.root` returns `ADFSPath(self, "$")` (`adfs/adfs.py:` analogous).

```python
# ADFS — clean.
adfs.root / "ReadMe"                # -> $.ReadMe

# DFS — surprising.
dfs.root / "$.HELLO"                # works
dfs.root / "HELLO"                  # produces "HELLO", not "$.HELLO"
```

The current `__truediv__` blindly concatenates with `.`, leaving the caller responsible for getting the `$.` prefix right.

**Proposed fix**

- `DFS.root` returns a path whose internal representation is `"$"`, matching ADFS.
- `DFSPath / "HELLO"` produces `"$.HELLO"` automatically.
- Existing `dfs.root / "$.HELLO"` usages must be migrated to `dfs.root / "HELLO"`.

> **Correction** (closed as won't-fix in [#27](https://github.com/rob-smallshire/oaknut/issues/27)):
> the analogy with ADFS is wrong. DFS is a *flat catalogue* whose
> per-file "directory" is a single-character namespace tag; `$`,
> `A`, `B`, … are **siblings**, not parent-and-children. `$` is the
> *default directory* DFS assumes when a path omits it, per the Acorn
> DFS User Guide. The current empty-string `dfs.root` correctly
> represents "the whole catalogue, no directory constraint", and
> `dfs.root / "A.GAME"` correctly produces `A.GAME`. Making `dfs.root`
> be `$` would silently lose that ability without admitting it. If
> sugar for the common `$` case is wanted, an explicit factory like
> `dfs.default_directory / "HELLO"` would be the honest spelling.

## 7. `DFS.from_file` requires explicit `disc_format`; `ADFS.from_file` auto-detects

**Where**:
- `DFS.from_file(filepath, disc_format, side=0)`
- `ADFS.from_file(filepath, *)`

DFS hosts the same kind of "is this `.ssd` or `.dsd` and 40T or 80T?" question that ADFS solves automatically — file size and extension are usually conclusive.

**Proposed fix**

- `DFS.from_file(filepath, *, disc_format=None, side=0)` — auto-detect when `disc_format is None`, otherwise honour the caller's choice.
- Detection rule: `.dsd` ⇒ double-sided; size ⇒ `80T`-or-`40T`; the existing `formats` module already encodes both.

## 8. `AFS.create_file` does not exist — `AFS.from_file` does

**Where**: `oaknut.afs.AFS` has `from_file` but no `create_file`. To create a new AFS image from scratch the user must compose `ADFS.create_file` + `oaknut.afs.wfsinit.initialise(adfs, spec=…)` + `oaknut.afs.libraries.emplace_library(afs, name)` themselves.

The CLI side already has `disc afs-init` for this. The Python side should not be more cumbersome.

**Proposed fix**

- Add `AFS.create_file(filepath, *, capacity=..., disc_name=..., users=..., emplacements=...)` as the symmetric constructor — orchestrates ADFS.create_file + initialise + emplace_library and yields the AFS handle.
- Cookbook recipe collapses from ~20 lines to ~6.

## 9. `capacity_bytes=10*1024*1024` is the only way to size a hard disc

**Where**: `ADFS.create_file(filepath, *, capacity_bytes=...)` (`adfs/adfs.py:1367`).

The CLI accepts `--capacity 10MB` and parses it; the Python API forces the user to compute bytes by hand.

**Proposed fix**

- Accept `capacity: int | str | None = None` — `int` is bytes (today's behaviour), `str` goes through the same capacity-string parser the CLI uses.
- Deprecate `capacity_bytes` as a separate kwarg.
- Same treatment for `quota` on `UserSpec` (currently `quota=2*1024*1024`).

## 10. AFS init is scattered across three submodules

**Where**: `oaknut.afs.wfsinit.initialise`, `oaknut.afs.wfsinit.{InitSpec,AFSSizeSpec,UserSpec}`, `oaknut.afs.libraries.emplace_library`.

The cookbook recipe imports from both `oaknut.afs.wfsinit` and `oaknut.afs.libraries`. A user trying to write a setup script has to know that disc layout is in one submodule and library emplacement in another — a distinction the library makes for its own internal architecture reasons, not the user's.

**Proposed fix**

- Re-export the public surface from `oaknut.afs.__init__`: `from oaknut.afs import initialise, InitSpec, AFSSizeSpec, UserSpec, emplace_library`.
- Once `AFS.create_file` (theme 8) lands, most callers never need these directly anyway — but the re-exports keep the lower-level building blocks reachable in one place.

## 11. `load_addr` vs `load_address`

**Where**: `oaknut.file.AcornMeta` uses `load_addr` / `exec_addr` / `attr`; everywhere else (`write_bytes`, `Stat.load_address`, `set-load`, `--load`) uses `load_address` / `exec_address` / `access`.

Two spellings for the same concept in the same package family.

**Proposed fix**

- Rename `AcornMeta` fields to `load_address` / `exec_address` / `access` (the longer, explicit, already-dominant forms).
- This is a public-facing change; consider a release note. Old field names can be kept as aliases for one release if backwards compatibility matters.

---

# Suggested sequencing

These changes are not all the same size; some are 10 lines, others touch several modules. Sequence so each step is reviewable on its own and the cookbook can be rewritten incrementally as each change lands.

1. **Foundational protocols** (theme 5, theme 11): define the `Stat` protocol, rename `AcornMeta` fields. No behavioural change. Establishes vocabulary.
2. **Symmetric path methods** (themes 1 & 2): add `AFSPath.export_file`, `DFSPath.import_file`, `AFSPath.import_file`. Pure additions.
3. **Polymorphic copy** (theme 3): drop `target_fs` from `copy_file`; have each path supply its own access mapping.
4. **Unified write_bytes signature** (theme 4): broaden `access` to accept `bool | Access | None` on every path class.
5. ~~**Root consistency** (theme 6): DFS root becomes `$`.~~ *Skipped — theme 6 was based on a misreading of DFS's flat catalogue; see the correction at the end of theme 6.*
6. **DFS auto-detect** (theme 7): make `disc_format` optional on `DFS.from_file` and `DFS.create_file`.
7. **AFS create + capacity strings** (themes 8, 9): new `AFS.create_file`; accept capacity strings on ADFS / AFS / UserSpec quota.
8. **AFS top-level re-exports** (theme 10): `oaknut.afs` exposes `initialise`, `InitSpec`, etc. directly.

After all eight steps, the API cookbook can be rewritten and each recipe becomes 5–10 lines of straight library use, no `oaknut.file` private-helper imports.
