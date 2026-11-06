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

__all__: list[str] = []
