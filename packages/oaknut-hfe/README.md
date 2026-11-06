# oaknut-hfe

[![PyPI version](https://img.shields.io/pypi/v/oaknut-hfe)](https://pypi.org/project/oaknut-hfe/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-hfe)](https://pypi.org/project/oaknut-hfe/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-hfe)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-hfe/LICENSE)

HFE (HxC Floppy Emulator) disc-image support for the
[oaknut](https://github.com/rob-smallshire/oaknut) family of packages.

An HFE file records each track of a floppy disc as the raw bitstream the
drive head delivers. It is the native format of the HxC and Gotek floppy
emulators and a common output of preservation capture hardware such as
the Greaseweazle. Because it sits below the sector level, an HFE image
keeps everything an original disc carries, including the non-standard
sector IDs, deliberate CRC errors, deleted-data marks and extra tracks
that copy protection relies on.

This package reads HFE v1 and v3 images, decodes their FM and MFM tracks
into sectors, and flattens a decoded disc into the logical sector image
that the oaknut filesystems read.

## Usage

Every `disc` command that reads an image opens an HFE file as the sector
image decoded from it:

```sh
disc ls 'Dunjunz_D1S1.hfe:$'
disc export Dunjunz_D1S1.hfe dunjunz/
```

The `disc hfe` commands look below the sector level:

```sh
disc hfe info Dunjunz_D1S1.hfe                 # header and decoded layout
disc hfe sectors --anomalies Dunjunz_D1S1.hfe  # what protection put there
disc hfe flatten Dunjunz_D1S1.hfe Dunjunz_D1S1.ssd
```

From Python:

```python
from oaknut.hfe import HFEImage, analyse, decode_image, flatten

disc = decode_image(HFEImage.from_filepath("Dunjunz_D1S1.hfe"))
flat = flatten(disc)  # flat.data is the .ssd image
for finding in analyse(disc, flat.layout):
    if finding.anomalous:
        print(finding.track, finding.side, finding.remarks)
```

## Status

Pre-alpha, read-only.

## Installation

```sh
uv add oaknut-hfe
```

## License

MIT — see [LICENSE](LICENSE).
