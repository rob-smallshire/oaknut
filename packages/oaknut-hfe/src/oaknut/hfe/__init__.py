"""HFE (HxC Floppy Emulator) flux-level disc images.

An HFE file records each track of a floppy disc as the raw bitstream a
drive's read head would deliver, sampled on a fixed cell clock. It is the
native format of the HxC and Gotek floppy emulators and a common output
of preservation capture hardware such as the Greaseweazle. Because it sits
below the sector level, an HFE image keeps everything an original disc
carries — including the non-standard sector IDs, deliberate CRC errors,
deleted-data marks and extra tracks that copy protection relies on.

This package reads HFE v1 (``HXCPICFE``) and v3 (``HXCHFEV3``) images,
decodes their FM and MFM tracks into sectors, and flattens a decoded disc
into the logical sector image that the oaknut filesystems read.
"""

from __future__ import annotations

__version__ = "13.5.0"

from oaknut.hfe.build import (
    TRACK_SAMPLES_300RPM_250KBPS,
    FormattedSector,
    build_track,
    samples_per_half_cell,
    track_samples,
)
from oaknut.hfe.container import (
    HFE_V1_SIGNATURE,
    HFE_V3_SIGNATURE,
    HFEHeader,
    HFEImage,
    TrackEncoding,
    TrackSamples,
    write_hfe,
)
from oaknut.hfe.decode import (
    DataMark,
    DecodedDisc,
    DecodedSector,
    DecodedTrack,
    Encoding,
    SectorID,
    decode_image,
    decode_track,
)
from oaknut.hfe.decoder import HFEDecoder
from oaknut.hfe.exceptions import HFEError, HFEFormatError
from oaknut.hfe.flat import FlatImage, SectorLayout, flatten, flatten_hfe
from oaknut.hfe.report import SectorFinding, TrackFinding, analyse

__all__ = [
    # The container
    "HFEImage",
    "HFEHeader",
    "TrackSamples",
    "TrackEncoding",
    "HFE_V1_SIGNATURE",
    "HFE_V3_SIGNATURE",
    "write_hfe",
    # Decoding
    "Encoding",
    "DataMark",
    "SectorID",
    "DecodedSector",
    "DecodedTrack",
    "DecodedDisc",
    "decode_track",
    "decode_image",
    # Flattening
    "SectorLayout",
    "FlatImage",
    "flatten",
    "flatten_hfe",
    # The sector report
    "SectorFinding",
    "TrackFinding",
    "analyse",
    # Building tracks
    "FormattedSector",
    "build_track",
    "track_samples",
    "samples_per_half_cell",
    "TRACK_SAMPLES_300RPM_250KBPS",
    # The oaknut.decoder plug-in
    "HFEDecoder",
    # Exceptions
    "HFEError",
    "HFEFormatError",
]
