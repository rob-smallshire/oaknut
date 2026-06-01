# oaknut-discimage

Sector-level disc-image abstractions shared by the oaknut filesystem
packages. This is the **geometry layer**: it turns a flat image file into
addressable sectors, and is deliberately blind to what those sectors
*mean*. The filing systems (`oaknut-dfs`, `oaknut-adfs`, `oaknut-afs`,
`oaknut-romfs`) build the sector→files layer on top of it.

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## The model

A disc image is a flat run of bytes; a filing system wants numbered
sectors. The mapping between the two is *physical geometry* — track
count, sector size, sidedness, interleave — and it is exactly what this
package models, in a small stack of abstractions that compose bottom-up:

```
raw bytes (mmap / bytearray)                  the image file
  ↓                                           described by
SurfaceSpec  ── one per surface ──            byte ⇄ sector geometry
  ↓                                           gathered into
DiscImage(buffer, [SurfaceSpec, …])           the whole image
  ↓  .surface(i)
Surface                                       one physical side
  ↓  .sector_range(start, count)
SectorsView                                   a read/write window of sectors
```

Above a `Surface`, a filing system reads and writes through the
`SectorsView` it hands back. Crucially that view is a *live* window onto
the backing buffer: writing through it lands in the mmap and thus on
disc. The package never copies sector data.

## The abstractions

### `SurfaceSpec` — the geometry of one surface

A frozen dataclass describing how one surface's sectors are laid out in
the image buffer:

| Field | Meaning |
|---|---|
| `num_tracks` | tracks on the surface (e.g. 40 or 80) |
| `sectors_per_track` | sectors per track (10 for Acorn DFS) |
| `bytes_per_sector` | usually 256 (`BYTES_PER_SECTOR`) |
| `track_zero_offset_bytes` | where this surface's track 0 begins in the buffer |
| `track_stride_bytes` | byte distance from one of this surface's tracks to the next |

The offset and stride are where **interleaving** lives. A single-sided
image is contiguous: offset 0, stride one track. An *interleaved*
double-sided image alternates the two sides track by track, so each
side's stride is two tracks and side 1 starts one track in. A
*sequential* double-sided image stores all of side 0 then all of side 1,
so side 1's offset is the whole first half. The layers above never see
any of this — they ask for logical sectors and the spec does the
arithmetic.

### `DiscImage` — the buffer plus its surfaces

`DiscImage(buffer, surface_specs)` pairs the raw `memoryview` with one or
more `SurfaceSpec`s, validates that the surfaces fit and do not overlap,
and vends a `Surface` per spec:

```python
image = DiscImage(buffer, specs)
side0 = image.surface(0)        # a Surface
image.num_surfaces              # 1 for SSD, 2 for DSD
```

### `Surface` — one physical side

A single side of the disc. Its job is to resolve a logical sector range
to the underlying bytes:

```python
view = side0.sector_range(start_sector=2, num_sectors=1)  # → SectorsView
side0.num_sectors, side0.num_tracks
```

### `SectorsView` — a logical buffer over sectors

Presents one or more (possibly non-contiguous, thanks to track stride)
memoryviews as a single addressable buffer. It indexes and slices like a
`bytearray`, and writes pass straight through to the backing image:

```python
view[0]                 # read a byte
view[0:8] = b"DISK    " # write — persists to the buffer (and the file)
view.tobytes()          # a plain bytes copy
```

This is the read/write surface every filing system actually operates on.

### `UnifiedDisc` — many surfaces as one address space

Some filing systems treat a double-sided disc as a *single* logical disc
with one continuous sector numbering (all of side 0, then all of side
1); others treat each side as an independent drive. `UnifiedDisc` is the
former view — it maps a unified sector number to the right
`(surface, sector)` pair and delegates to `Surface`:

```python
disc = UnifiedDisc(image)
disc.sector_range(start_sector, num_sectors)   # spans both sides seamlessly
```

ADFS reads a double-sided floppy through a `UnifiedDisc`; DFS, where each
side is a separate `*DRIVE`, talks to each `Surface` directly. For a
single-sided disc a `UnifiedDisc` is a trivial pass-through.

### `DiscFormat` — geometry plus filing system

`DiscFormat(surface_specs, catalogue_name)` is a complete format: the
surface layout together with the name of the filing system that lives on
it. Filesystem packages compose these into named constants and ship them
alongside the filing system they describe — for example
`oaknut.dfs.formats.ACORN_DFS_80T_SINGLE_SIDED`.

### Geometry helpers

Building `SurfaceSpec` lists by hand is fiddly, so the common layouts
have constructors:

- `single_sided_spec(num_tracks, sectors_per_track, bytes_per_sector=256)`
- `interleaved_double_sided_specs(...)`
- `sequential_double_sided_specs(...)`

`BYTES_PER_SECTOR` (256) is the Acorn sector size, and
`open_image_mmap(path)` opens an image with the right access — writable
when the host file permits, read-only otherwise (mutations then raise at
the mmap layer), so DFS, ADFS, and AFS all behave identically.

## Putting it together

```python
from oaknut.discimage import DiscImage, single_sided_spec

buffer = memoryview(bytearray(b"\x00" * (80 * 10 * 256)))  # 80T × 10 sectors
image = DiscImage(buffer, [single_sided_spec(num_tracks=80, sectors_per_track=10)])

surface = image.surface(0)
sector0 = surface.sector_range(0, 1)
sector0[0:8] = b"MYDISC  "          # write the catalogue title into sector 0
assert bytes(buffer[0:8]) == b"MYDISC  "   # it landed in the backing buffer
```

## Relationship to the rest of oaknut

This package owns the **physical** mapping (bytes ⇄ sectors); a *filing
system* owns the **logical** mapping (sectors ⇄ files and directories).
That separation mirrors `oaknut-filesystem`, whose `Geometry` /
`Filesystem` split sits one level up: a filing system reads logical
sectors and is blind to interleave, sidedness, and on-disc byte offsets —
all of which live here.

## Licence

MIT.
