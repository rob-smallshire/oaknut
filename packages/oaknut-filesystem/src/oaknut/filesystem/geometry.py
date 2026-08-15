"""Geometry — the *physical* layout of an image, beneath the filesystem.

Geometry says how image bytes map to logical sectors: track count,
sides, interleave, density, or a hard disc's cylinders/heads/SPT. It is
deliberately separate from the *filesystem* (the logical structure on
those sectors) and carries no catalogue notion — unlike the discimage
``DiscFormat``, which bundles a catalogue name. A :class:`Geometry` is
essentially the surface-spec list a filesystem will be read through.

Because floppies enumerate as a handful of named presets but hard discs
span an open-ended CHS space, geometry is chosen through a
:class:`GeometryGrammar`: named presets plus a parameterised form.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from oaknut.discimage import (
    BYTES_PER_SECTOR,
    DiscImage,
    SurfaceSpec,
    UnifiedDisc,
    interleaved_double_sided_specs,
    sequential_double_sided_specs,
    single_sided_spec,
)
from oaknut.filesystem.exceptions import GeometryError
from oaknut.filesystem.reader import ImageReader

#: The parameterised geometry kinds the built-in grammar understands.
FLOPPY = "floppy"
WINCHESTER = "winchester"


@dataclass(frozen=True)
class Geometry:
    """A physical layout: the surface specs an image is read through.

    Pure geometry — no catalogue or filesystem. ``label`` is a short
    human description (e.g. ``"ADFS-L (80T DS interleaved)"``).

    ``cylinders``/``heads``/``sectors_per_track`` are the optional CHS the
    layout was built from — a hard disc's, carried so a filesystem can
    *report* it (the surface specs themselves linearise CHS away). They
    are ``None`` when the source did not record CHS.

    ``variant`` is an optional filesystem-specific format tag a geometry was
    requested as, for the cases where several logical formats share one
    physical size and so cannot be told apart by geometry alone (ADFS D, E
    and E+ are all 800K; F and F+ are both 1.6M; G and G+ are both 3.2M).
    A filesystem's ``create`` reads it to pick the on-disc layout. It is
    ``None`` for geometries that are unambiguous by size.
    """

    surface_specs: tuple[SurfaceSpec, ...]
    label: str = ""
    cylinders: int | None = None
    heads: int | None = None
    sectors_per_track: int | None = None
    variant: str | None = None

    def __post_init__(self) -> None:
        if not self.surface_specs:
            raise GeometryError("a geometry needs at least one surface spec")

    @property
    def image_size(self) -> int:
        """Total bytes a full image in this geometry occupies."""
        end = 0
        for spec in self.surface_specs:
            bytes_per_track = spec.sectors_per_track * spec.bytes_per_sector
            spec_end = (
                spec.track_zero_offset_bytes
                + (spec.num_tracks - 1) * spec.track_stride_bytes
                + bytes_per_track
            )
            end = max(end, spec_end)
        return end

    @property
    def num_sectors(self) -> int:
        """Total logical sectors across all surfaces."""
        return sum(spec.num_tracks * spec.sectors_per_track for spec in self.surface_specs)


def floppy_geometry(
    *,
    tracks: int,
    sides: int,
    sectors_per_track: int = 10,
    bytes_per_sector: int = BYTES_PER_SECTOR,
    interleaved: bool = True,
    label: str = "",
    variant: str | None = None,
) -> Geometry:
    """Build a floppy :class:`Geometry`.

    *sides* is 1 or 2; for double-sided, *interleaved* selects the
    Acorn-conventional interleaved layout (side 0/side 1 alternating per
    track) over the sequential one. *variant* tags a format that shares its
    physical size with a sibling (see :class:`Geometry`).
    """
    if sides == 1:
        specs = [single_sided_spec(tracks, sectors_per_track, bytes_per_sector)]
    elif sides == 2:
        builder = interleaved_double_sided_specs if interleaved else sequential_double_sided_specs
        specs = builder(tracks, sectors_per_track, bytes_per_sector)
    else:
        raise GeometryError(f"floppy sides must be 1 or 2, got {sides}")
    return Geometry(tuple(specs), label=label, variant=variant)


def winchester_geometry(
    *,
    cylinders: int,
    heads: int,
    sectors_per_track: int,
    bytes_per_sector: int = BYTES_PER_SECTOR,
    label: str = "",
) -> Geometry:
    """Build a hard-disc :class:`Geometry` as one linear sector surface.

    Acorn hard-disc images present a flat linear sector space; the CHS
    figures determine its extent. (They are also recorded in a ``.dsc``
    sidecar, but the image itself is linear.)
    """
    total_sectors = cylinders * heads * sectors_per_track
    if total_sectors <= 0:
        raise GeometryError(
            f"winchester geometry needs positive cylinders/heads/spt, got "
            f"{cylinders}/{heads}/{sectors_per_track}"
        )
    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=total_sectors,
        bytes_per_sector=bytes_per_sector,
        track_zero_offset_bytes=0,
        track_stride_bytes=total_sectors * bytes_per_sector,
    )
    return Geometry(
        (spec,),
        label=label or f"{cylinders}c/{heads}h/{sectors_per_track}s",
        cylinders=cylinders,
        heads=heads,
        sectors_per_track=sectors_per_track,
    )


#: A hard-disc ``.dsc`` sidecar is 22 bytes of SCSI MODE SENSE geometry:
#: cylinders as a big-endian 16-bit at offset 13, head count at offset 15.
#: SPT is not recorded and is conventionally 33 for Acorn SCSI discs.
_DSC_SIZE = 22
_DSC_DEFAULT_SPT = 33


def geometry_from_dsc(dsc_bytes: bytes, *, sectors_per_track: int = _DSC_DEFAULT_SPT) -> Geometry:
    """Build a hard-disc :class:`Geometry` from a 22-byte ``.dsc`` sidecar.

    Geometry resolution, not filesystem identification: the ``.dsc``
    carries the CHS a hard-disc image's bytes cannot, so the caller can
    report it. Raises :class:`GeometryError` on a malformed sidecar.
    """
    if len(dsc_bytes) < _DSC_SIZE:
        raise GeometryError(f".dsc sidecar must be at least {_DSC_SIZE} bytes")
    cylinders = (dsc_bytes[13] << 8) | dsc_bytes[14]
    heads = dsc_bytes[15]
    if cylinders <= 0 or heads <= 0:
        raise GeometryError(f"malformed .dsc geometry: {cylinders} cylinders, {heads} heads")
    return winchester_geometry(
        cylinders=cylinders, heads=heads, sectors_per_track=sectors_per_track
    )


def _parse_params(spec: str) -> dict[str, str]:
    """Parse a ``key=value,key=value`` geometry spec into a dict."""
    params: dict[str, str] = {}
    for field_text in spec.split(","):
        field_text = field_text.strip()
        if not field_text:
            continue
        key, sep, value = field_text.partition("=")
        if not sep:
            raise GeometryError(f"geometry field {field_text!r} is not key=value")
        params[key.strip().lower()] = value.strip()
    return params


@dataclass(frozen=True)
class GeometryGrammar:
    """How a filesystem accepts a geometry on the command line / API.

    *presets* are the enumerable named layouts (``s``/``m``/``l`` for
    ADFS floppies); *kinds* are the parameterised forms it also accepts
    (``floppy`` and/or ``winchester``). :meth:`parse` resolves a string
    to a :class:`Geometry`, trying a preset name first, then a
    parameterised ``key=value`` form.
    """

    presets: Mapping[str, Geometry] = field(default_factory=dict)
    kinds: tuple[str, ...] = ()

    def preset_names(self) -> list[str]:
        return sorted(self.presets)

    def parse(self, spec: str) -> Geometry:
        key = spec.strip().lower()
        if key in self.presets:
            return self.presets[key]

        # A bare word (no '=') is a mistyped preset, not a parameterised
        # form — name what this filesystem actually accepts rather than
        # complain about key=value syntax.
        if "=" not in spec:
            raise GeometryError(self._unknown_geometry_message(spec))

        params = _parse_params(spec)
        if {"cylinders", "heads", "capacity"} & params.keys():
            if WINCHESTER not in self.kinds:
                raise GeometryError("this filesystem does not accept hard-disc geometry")
            return self._winchester(params)
        if {"tracks", "sides"} & params.keys():
            if FLOPPY not in self.kinds:
                raise GeometryError("this filesystem does not accept floppy geometry")
            return self._floppy(params)

        raise GeometryError(self._unknown_geometry_message(spec))

    def _unknown_geometry_message(self, spec: str) -> str:
        """A geometry error that lists what this filesystem actually accepts."""
        options: list[str] = []
        if self.presets:
            options.append("presets " + ", ".join(self.preset_names()))
        if WINCHESTER in self.kinds:
            options.append("capacity=SIZE or cylinders=N,heads=N,spt=N")
        if FLOPPY in self.kinds:
            options.append("tracks=N,sides=N[,interleave=interleaved|sequential]")
        accepts = "; ".join(options) or "no geometry (this filesystem has none)"
        return f"cannot parse geometry {spec!r}; accepts: {accepts}"

    def _floppy(self, params: dict[str, str]) -> Geometry:
        try:
            tracks = int(params["tracks"])
            sides = int(params["sides"])
        except (KeyError, ValueError) as exc:
            raise GeometryError(f"floppy geometry needs integer tracks and sides: {exc}") from exc
        interleave = params.get("interleave", "interleaved").lower()
        if interleave not in ("interleaved", "sequential"):
            raise GeometryError(f"interleave must be interleaved|sequential, got {interleave!r}")
        return floppy_geometry(
            tracks=tracks,
            sides=sides,
            sectors_per_track=int(params.get("spt", "10")),
            interleaved=(interleave == "interleaved"),
        )

    def _winchester(self, params: dict[str, str]) -> Geometry:
        import math

        from oaknut.discimage import BYTES_PER_SECTOR
        from oaknut.file.capacity import parse_capacity

        try:
            heads = int(params.get("heads", "4"))
            sectors_per_track = int(params.get("spt", params.get("sectors", "33")))
            if "capacity" in params:
                # Derive the cylinder count that covers the requested
                # capacity at the chosen (or default) heads/SPT.
                capacity_bytes = parse_capacity(params["capacity"])
                per_cylinder = heads * sectors_per_track * BYTES_PER_SECTOR
                cylinders = max(1, math.ceil(capacity_bytes / per_cylinder))
            else:
                cylinders = int(params["cylinders"])
            return winchester_geometry(
                cylinders=cylinders, heads=heads, sectors_per_track=sectors_per_track
            )
        except (KeyError, ValueError) as exc:
            raise GeometryError(
                f"hard-disc geometry needs a capacity, or integer cylinders/heads/spt: {exc}"
            ) from exc


def _is_linear(geometry: Geometry) -> bool:
    """Whether logical sector *i* maps to byte ``i*256`` contiguously.

    True for a hard disc's single linear surface; false for an
    interleaved double-sided floppy whose two sides alternate per track.
    """
    specs = geometry.surface_specs
    if len(specs) != 1:
        return False
    spec = specs[0]
    return spec.num_tracks == 1 and spec.track_zero_offset_bytes == 0


def region_reader(
    reader: ImageReader,
    geometry: Geometry | None,
    start_sector: int,
    num_sectors: int,
) -> ImageReader:
    """A reader over the *logical sector* run ``[start_sector, +num_sectors)``.

    When the host is linear (no geometry, or a single contiguous surface
    — a hard disc), the run is a byte window that shares the backing, so
    it is cheap and inherits the host's writability: writes to a tail
    filesystem reach the file. When the host is interleaved (a
    double-sided floppy) the run's bytes are scattered, so the host's
    :class:`~oaknut.discimage.UnifiedDisc` de-interleaves them into a
    contiguous view a tail filesystem can address linearly. That view is
    a copy, so it is read-only: writing to an interleaved reserved region
    would not reach the file, and is refused rather than silently lost.
    """
    if geometry is None or _is_linear(geometry):
        return reader.window(start_sector * BYTES_PER_SECTOR, num_sectors * BYTES_PER_SECTOR)
    if reader.writable:
        raise GeometryError(
            "writing to an interleaved reserved region (e.g. AFS on a "
            "double-sided floppy) is not yet supported; the region must be "
            "de-interleaved into a copy, which cannot write back live"
        )
    buffer = memoryview(bytearray(reader.read(0, reader.size)))
    disc = UnifiedDisc(DiscImage(buffer, list(geometry.surface_specs)))
    view = disc.sector_range(start_sector, num_sectors)
    return ImageReader(bytes(view[:]))
