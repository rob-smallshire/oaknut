"""Tests for DFS host (I/O processor) load/exec address expansion.

A DFS catalogue stores load and execution addresses as 18-bit values
(16 bits plus two high bits packed into the shared "extra" byte). When
the top two bits are both set, the address denotes a host I/O-processor
address and Acorn MOS expands the top byte to ``FF`` — so ``*EX``/``*INFO``
print a value such as ``FFFFFF`` where the raw 18-bit field holds
``0x3FFFF``. oaknut reconstructs the same expanded address on read so its
output matches the machine.
"""

from __future__ import annotations

import pytest
from oaknut.dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut.discimage.surface import DiscImage, SurfaceSpec

_REFERENCE = "host-address/weekend-challenge.ssd"

# Acorn *EX of the reference disc: load, exec for each file.
_EXPECTED = {
    "TriDeep": (0x001900, 0x00838F),
    "TEX5": (0x000000, 0xFFFFFF),
    "TEX3": (0x000000, 0xFFFFFF),
    "T2": (0x001900, 0x00838F),
    "TRITEX2": (0x000000, 0xFFFFFF),
    "TRITEXT": (0x000000, 0xFFFFFF),
    "Triang": (0x001900, 0x00838F),
}


class TestReferenceDisc:
    def test_exec_addresses_match_acorn_ex(self, reference_image):
        disk = reference_image(_REFERENCE)
        by_name = {entry.filename: entry for entry in disk.files}
        for name, (load, exec_) in _EXPECTED.items():
            assert name in by_name, f"{name} missing from catalogue"
            assert by_name[name].load_address == load, name
            assert by_name[name].exec_address == exec_, name


def _build_entry_buffer(load_low: int, exec_low: int, extra_byte: int) -> DiscImage:
    """A minimal valid Acorn DFS image carrying a single catalogue entry."""
    buffer = bytearray(102400)
    buffer[0:8] = b"HOSTADDR"
    buffer[256:260] = b"    "
    # sector1[5] holds (number of files × 8): one file → 0x08.
    buffer[261] = 0x08
    buffer[262] = 0x01  # total-sector count high bits (400 = 0x190)
    buffer[263] = 0x90  # total-sector count low byte
    # Catalogue name slot (sector 0) for the single file.
    buffer[8] = ord("F")
    buffer[9:15] = b"      "
    buffer[15] = ord("$")
    # Address/length slot (sector 1).
    buffer[264] = load_low & 0xFF
    buffer[265] = (load_low >> 8) & 0xFF
    buffer[266] = exec_low & 0xFF
    buffer[267] = (exec_low >> 8) & 0xFF
    buffer[268] = 0x00  # length low
    buffer[269] = 0x00
    buffer[270] = extra_byte
    buffer[271] = 0x02  # start sector
    spec = SurfaceSpec(
        num_tracks=40,
        sectors_per_track=10,
        bytes_per_sector=256,
        track_zero_offset_bytes=0,
        track_stride_bytes=2560,
    )
    return DiscImage(memoryview(buffer), [spec])


class TestTopBitExpansion:
    def test_both_top_bits_set_expands_exec_top_byte(self):
        # exec low = 0xFFFF, exec high bits (extra & 0xC0) = 0b11.
        disc = _build_entry_buffer(load_low=0x0000, exec_low=0xFFFF, extra_byte=0xC0)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.exec_address == 0xFFFFFF

    def test_top_bits_clear_leaves_address_unchanged(self):
        disc = _build_entry_buffer(load_low=0x838F, exec_low=0x1900, extra_byte=0x00)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.load_address == 0x838F
        assert entry.exec_address == 0x1900

    def test_single_top_bit_set_is_not_expanded(self):
        # Only bit 17 of exec set (extra & 0xC0 == 0x80): not the host
        # convention, so no top-byte expansion.
        disc = _build_entry_buffer(load_low=0x0000, exec_low=0xFFFF, extra_byte=0x80)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.exec_address == 0x2FFFF


class TestRoundTrip:
    def test_expanded_exec_round_trips(self, writable_copy):
        disk, _ = writable_copy(_REFERENCE)
        (disk.root / "$" / "HOSTX").write_bytes(
            b"payload", load_address=0xFFFFFF, exec_address=0xFFFFFF
        )
        reread = (disk.root / "$" / "HOSTX").stat()
        assert reread.load_address == 0xFFFFFF
        assert reread.exec_address == 0xFFFFFF


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
