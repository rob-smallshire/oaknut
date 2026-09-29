"""Tests for DFS host (I/O processor) load/exec address expansion.

A DFS catalogue stores load and execution addresses as 18-bit values
(16 bits plus two high bits packed into the shared "extra" byte). When
the top two bits are both set, the address denotes a host I/O-processor
address, and DFS returns it through OSFILE as the 32-bit ``&FFFFxxxx``
(DFS 2.24 ``.decode``: "if b7,b6 both set then a host address, set high
word = $FFFF"; otherwise a parasite address ``&0..2FFFF``). ``*EX`` and
``*INFO`` print only the low three bytes, so ``&FFFFFFFF`` shows as
``FFFFFF``. oaknut reads the full OSFILE value, so a copy to a 32-bit
filing system keeps the address in the I/O processor (issue #61).
"""

from __future__ import annotations

import pytest
from oaknut.dfs.acorn_dfs_catalogue import AcornDFSCatalogue
from oaknut.discimage.surface import DiscImage, SurfaceSpec

_REFERENCE = "host-address/weekend-challenge.ssd"

# The OSFILE load, exec of each file on the reference disc. Acorn *EX
# prints the low three bytes of each (so FFFFFF for the host addresses).
_EXPECTED = {
    "TriDeep": (0x001900, 0x00838F),
    "TEX5": (0x000000, 0xFFFFFFFF),
    "TEX3": (0x000000, 0xFFFFFFFF),
    "T2": (0x001900, 0x00838F),
    "TRITEX2": (0x000000, 0xFFFFFFFF),
    "TRITEXT": (0x000000, 0xFFFFFFFF),
    "Triang": (0x001900, 0x00838F),
}


class TestReferenceDisc:
    def test_addresses_match_osfile(self, reference_image):
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
    def test_both_top_bits_set_expands_to_host_high_word(self):
        # exec low = 0x2000, exec high bits (extra & 0xC0) = 0b11.
        disc = _build_entry_buffer(load_low=0x0000, exec_low=0x2000, extra_byte=0xC0)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.exec_address == 0xFFFF2000

    def test_load_address_expands_the_same_way(self):
        # load high bits (extra & 0x0C) = 0b11.
        disc = _build_entry_buffer(load_low=0x1900, exec_low=0x0000, extra_byte=0x0C)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.load_address == 0xFFFF1900

    def test_top_bits_clear_leaves_address_unchanged(self):
        disc = _build_entry_buffer(load_low=0x838F, exec_low=0x1900, extra_byte=0x00)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.load_address == 0x838F
        assert entry.exec_address == 0x1900

    def test_single_top_bit_set_is_not_expanded(self):
        # Only bit 17 of exec set (extra & 0xC0 == 0x80): a parasite
        # address in &0..2FFFF, so not expanded — this is not sign extension.
        disc = _build_entry_buffer(load_low=0x0000, exec_low=0xFFFF, extra_byte=0x80)
        catalogue = AcornDFSCatalogue(disc.surface(0))
        entry = catalogue.list_files()[0]
        assert entry.exec_address == 0x2FFFF


class TestRoundTrip:
    def test_host_address_round_trips(self, writable_copy):
        disk, _ = writable_copy(_REFERENCE)
        (disk.root / "$" / "HOSTX").write_bytes(
            b"payload", load_address=0xFFFF1900, exec_address=0xFFFF8023
        )
        reread = (disk.root / "$" / "HOSTX").stat()
        assert reread.load_address == 0xFFFF1900
        assert reread.exec_address == 0xFFFF8023

    @pytest.mark.parametrize("written", [0x31900, 0xFF1900, 0xFFFF1900])
    def test_every_host_form_reads_back_as_osfile_value(self, writable_copy, written):
        # The raw 18-bit form, the *INFO-printed form and the OSFILE form all
        # set both high bits, so all store the same host address.
        disk, _ = writable_copy(_REFERENCE)
        (disk.root / "$" / "HOSTY").write_bytes(b"x", load_address=written)
        assert (disk.root / "$" / "HOSTY").stat().load_address == 0xFFFF1900


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
