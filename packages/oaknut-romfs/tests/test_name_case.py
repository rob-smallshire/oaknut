"""ROMFS preserves filename case and matches it case-sensitively.

ROMFS stores CFS names verbatim (no case folding anywhere) and the
cassette filing system compares names byte-for-byte, so a name keeps its
case and a differently-cased query does not find it — unlike the
disc filing systems, whose matching is case-insensitive.
"""

from __future__ import annotations

import pytest
from oaknut.filesystem import reader_for
from oaknut.romfs.exceptions import ROMFSError
from oaknut.romfs.filesystem import AcornROMFS
from oaknut.romfs.romfs import ROMFS, build_rom_image


def _writable_mount():
    data = bytearray(build_rom_image(title="DISC", size=16384))
    reader = reader_for(data, writable=True)
    fs = AcornROMFS()
    mount = fs.open(reader, fs.probe(reader).geometry)
    return mount, data


def test_mixed_case_name_stored_verbatim():
    mount, data = _writable_mount()
    mount.write_bytes("MixedCase", b"x")

    names = [f.name for f in ROMFS.from_bytes(bytes(data)).data_files]
    assert "MixedCase" in names
    assert "MIXEDCASE" not in names


def test_lookup_is_case_sensitive():
    mount, _data = _writable_mount()
    mount.write_bytes("MixedCase", b"data")

    assert mount.read_bytes("MixedCase") == b"data"
    # ROMFS matches byte-for-byte, so a different case is a different name.
    with pytest.raises(ROMFSError):
        mount.read_bytes("MIXEDCASE")
