# Proposal: deterministic mmap teardown via context-managed buffer ownership

Status: draft for review (branch `mmap-close-on-exit`). No production code changed yet.

## Symptom

On Windows, after `disc create` or any writable open, the image file stays
locked until the process exits — you cannot overwrite, move or delete it.
Surfaced as `OSError [Errno 22]` in the new control-character tests (worked
around there by writing fixtures to fresh paths).

## Root cause (validated on macOS — the mechanism is platform-independent)

The writable open path memory-maps the file and hands a **borrowed
`memoryview`** down a chain that never releases it:

```
mmap.mmap(file)                                   # the OS resource
  └─ memoryview(mm)            reader.buffer() / create_file            (root view)
       └─ DiscImage._buffer    surface.py:141                           (held for the mount's life)
            └─ self._buffer[a:b]  DiscImage.sector_views()              (transient slices…)
                 └─ SectorsView._views                                  (…not retained by the catalogue)
```

`mmap.close()` raises `BufferError: cannot close exported pointers exist`
while *any* of those views is alive. Two places then make it silent:

- `ImageReader.close()` (reader.py:150) closes its closeables under
  `with suppress(Exception)` — so the `BufferError` from `mapping.close()`
  is swallowed and the mmap is **never closed**.
- `DFS.create_file` (dfs.py:972) and `open_image_mmap` (open_image.py:52)
  only `mm.flush()` in their `finally` — there is no `mm.close()` at all.

Because the mount object graph (DFS → CataloguedSurface → Surface →
DiscImage._buffer) keeps the root view alive, nothing is ever released.
POSIX tolerates closing the fd with a live mapping; Windows locks the file.

Proof (real mount):

```
before:                       mapping.closed = False
after reader.close():         mapping.closed = False     # leaked, silently
after _buffer.release() + mapping.close():  mapping.closed = True
```

## Design: make buffer ownership a context-managed contract

The fix your instinct points at: the thing that **owns** the mmap is a
context manager that closes it on exit, and every layer that **borrows**
its `memoryview` releases that borrow on its own exit — innermost first,
so by the time the owner closes the mmap there are no live views.

Ownership today is already mostly context-managed; what's missing is the
*release of the borrowed view* and the *ordering*.

1. **`DiscImage` releases what it borrowed.** Add `close()` (+ `__enter__`/
   `__exit__`) that calls `self._buffer.release()` and drops `self._surfaces`.
   Idempotent. `Surface`/`SectorsView` hold no persistent views, so nothing
   else needs releasing — but `SectorsView` gains a `release()` too for the
   rare caller that retains one.

2. **The mount/DFS owns its DiscImage.** `DFS.close()` (today just sets a
   flag) also closes its `DiscImage`. `_DFSMount`/`ResolvedMount` already
   exist as context managers; `ResolvedMount.close()` closes the **mount
   first, then the reader** — borrower before owner.

3. **`ImageReader.close()` stops hiding the error.** Once borrowers release
   first, `mapping.close()` succeeds. Drop the blanket `suppress(Exception)`
   (or narrow it) so a future leak surfaces loudly instead of silently
   relocking files on Windows.

4. **The creation/`from_file` paths close the mmap.** `DFS.create_file` and
   `DFS.from_file` (and the ADFS equivalents) release the DiscImage buffer
   and `mm.close()` in their `finally`, not just `flush()`.

Resulting usage is plain nested context managers:

```python
with reader_for(path, writable=True) as reader:   # owns the mmap
    with fs.open(reader, geometry) as mount:       # borrows the buffer
        ...                                          # use the mount
    # mount.__exit__ → DiscImage._buffer.release()
# reader.__exit__ → mapping.close() now succeeds (no live views)
```

## Affected sites

- `oaknut-filesystem/.../reader.py` — `ImageReader.close()` ordering + stop suppressing.
- `oaknut-discimage/.../surface.py` — `DiscImage.close()`/`__exit__`, buffer release.
- `oaknut-discimage/.../sectors_view.py` — optional `release()`.
- `oaknut-dfs/.../dfs.py` — `DFS.close()` releases DiscImage; `create_file`/`from_file` finally → `mm.close()`.
- `oaknut-adfs/.../adfs.py` — same pattern at lines 1218/1451/1462 (mirror the DFS fix).
- `oaknut-disc/.../mount.py` — `ResolvedMount.close()` closes mount before reader.
- `oaknut-romfs` — audit `block.py:118` (appears to be a private `bytes`, likely fine).

## Test strategy (no Windows needed)

The `BufferError`/`mmap.closed` mechanism is platform-independent, so a
deterministic regression test runs everywhere:

```python
reader = reader_for(path, writable=True)
with fs.open(reader, geom) as mount:
    ...
reader.close()
assert reader._closeables == ()           # closed
assert mapping.closed is True             # the real assertion — fails today
```

This fails on macOS/Linux today (mapping stays open) and passes after the
fix — TDD without a Windows runner. Add a Windows-only test that creates an
image and then deletes/overwrites it in-place to lock in the user-visible
behaviour.

## Risks / edge cases

- **Caller retains a `SectorsView`**: releasing `DiscImage._buffer` while a
  sub-view is alive raises `BufferError`. In normal mount use, catalogue
  reads are transient, so none are alive at close. `SectorsView.release()`
  covers the deliberate-retention case.
- **Padded/truncated buffers**: `_pad_buffer` may return a private
  `bytearray` memoryview (not over the mmap); releasing it is harmless, and
  the mmap then has no live borrower.
- **Read-only path**: `buffer()` already returns a private copy, so the
  mmap has no exported views — closing already works; the fix just makes it
  uniform.
- **Windows of the same reader**: `window()` shares `_data` but does not own
  it (`close()` is a no-op on a window) — unchanged.

## Suggested sequencing

1. Land the cross-platform failing test (asserts `mapping.closed`).
2. `DiscImage.close()` + `DFS.close()` release + `ResolvedMount` ordering →
   green on the reader path.
3. `create_file`/`from_file` finally → `mm.close()`.
4. Mirror in ADFS.
5. Drop the `suppress` in `ImageReader.close()` last, once nothing leaks.
