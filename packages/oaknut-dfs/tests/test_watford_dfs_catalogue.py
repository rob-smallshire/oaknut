"""Tests for Watford DFS Catalogue implementation."""

import pytest
from oaknut.dfs.catalogue import Catalogue
from oaknut.dfs.watford_dfs_catalogue import WatfordDFSCatalogue
from oaknut.discimage.surface import DiscImage, SurfaceSpec


@pytest.fixture
def watford_dfs_surface():
    """Create a valid Watford DFS surface for testing."""
    buffer = bytearray(204800)  # 80-track single-sided (800 sectors × 256 bytes)

    # Initialize sector 0 (section 1 title in bytes 0-9)
    buffer[0:10] = b"WATFORD   "  # 10-char title (7 letters + 3 spaces)
    buffer[10:12] = b"\x00\x00"  # Bytes 10-11 reserved for catalog chaining

    # Initialize sector 1 (section 1 metadata - no title continuation)
    buffer[256:260] = b"\x00\x00\x00\x00"  # First 4 bytes (no title in Watford DFS)
    buffer[256 + 4] = 0  # Cycle number
    buffer[256 + 5] = 0  # 0 files (bits 0,1,2 must be clear)
    buffer[256 + 6] = 0x03  # Boot option 0, 800 sectors high bits (0x03)
    buffer[256 + 7] = 0x20  # 800 sectors low byte (0x320 = 800)

    # Initialize sector 2 (0xAA marker - Watford DFS signature)
    buffer[512:524] = b"\xaa" * 12

    # Initialize sector 3 (section 2 metadata)
    buffer[768:772] = b"\x00\x00\x00\x00"  # First 4 bytes null
    buffer[768 + 4] = 0  # Cycle number (matches section 1)
    buffer[768 + 5] = 0  # 0 files in section 2
    buffer[768 + 6] = 0x03  # Boot option 0, sector count high (matches section 1)
    buffer[768 + 7] = 0x20  # Sector count low (matches section 1)

    spec = SurfaceSpec(
        num_tracks=80,
        sectors_per_track=10,
        bytes_per_sector=256,
        track_zero_offset_bytes=0,
        track_stride_bytes=2560,  # 10 sectors × 256 bytes
    )
    disc = DiscImage(memoryview(buffer), [spec])
    return disc.surface(0)


class TestWatfordDFSCatalogueRegistry:
    """Test Watford DFS catalogue registration."""

    def test_watford_dfs_registered(self):
        """Verify Watford DFS is registered in catalogue registry."""
        assert "watford-dfs" in Catalogue._registry
        assert Catalogue._registry["watford-dfs"] is WatfordDFSCatalogue

    def test_identify_returns_watford_dfs_for_valid_image(self, watford_dfs_surface):
        """Test that identify() returns WatfordDFSCatalogue for valid image."""
        result = Catalogue.identify(watford_dfs_surface)
        assert result is WatfordDFSCatalogue

    def test_identify_returns_none_for_acorn_dfs_image(self):
        """Test that Watford DFS doesn't match Acorn DFS images."""
        buffer = bytearray(102400)  # 40-track single-sided
        buffer[0:12] = b"ACORNDFS    "  # No 0xAA marker
        buffer[256 + 5] = 0
        buffer[256 + 6] = 0x01
        buffer[256 + 7] = 0x90  # 400 sectors

        spec = SurfaceSpec(
            num_tracks=40,
            sectors_per_track=10,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=2560,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        # Should not match Watford DFS (no 0xAA marker)
        assert not WatfordDFSCatalogue.matches(surface)


class TestWatfordDFSCatalogueMatches:
    """Test Watford DFS format detection."""

    def test_matches_valid_watford_dfs(self, watford_dfs_surface):
        """Test matches() returns True for valid Watford DFS image."""
        assert WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_matches_rejects_missing_aa_marker(self, watford_dfs_surface):
        """Test matches() rejects image without 0xAA marker."""
        # Clear the 0xAA marker
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[512:524] = b"\x00" * 12

        assert not WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_matches_rejects_metadata_mismatch(self, watford_dfs_surface):
        """Test matches() rejects image with mismatched metadata between sections."""
        # Change sector 3 metadata to not match sector 1
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[768 + 6] = 0x00  # Different from sector 1

        assert not WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_matches_with_files_in_section_one_only(self, tmp_path):
        """A Watford disc with files only in section 1 has unequal per-section
        file counts (section 2 empty), yet must still identify — the two
        section counts are independent, not mirrored. Regression: matches()
        wrongly required sector3[5] == sector1[5], so any non-empty disc with
        files in just one section failed to identify.
        """
        from oaknut.dfs.dfs import DFS
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        image_filepath = tmp_path / "section1.ssd"
        with DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED, title="Telem") as dfs:
            for i in range(31):  # exactly fills section 1, leaves section 2 empty
                (dfs.root / f"$.F{i:02d}").write_bytes(b"x")
        with DFS.from_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED) as dfs:
            surface = dfs._catalogued_surface._surface
            assert WatfordDFSCatalogue.matches(surface)

    def test_matches_with_files_in_both_sections(self, tmp_path):
        """A Watford disc with files in section 2 must still identify. The
        0xAA marker occupies only sector 2 bytes 0-7 (section 2's 8-byte
        title slot); file entries begin at byte 8, so a populated section 2
        overwrites bytes 8+. Regression: the marker check read 12 bytes, so
        the first section-2 file's name broke identification.
        """
        from oaknut.dfs.dfs import DFS
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        image_filepath = tmp_path / "both.ssd"
        with DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED, title="Telem") as dfs:
            for i in range(40):  # 31 in section 1, 9 spill into section 2
                (dfs.root / f"$.F{i:02d}").write_bytes(b"x")
        with DFS.from_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED) as dfs:
            surface = dfs._catalogued_surface._surface
            assert WatfordDFSCatalogue.matches(surface)
            assert dfs.validate() == []
            assert len(dfs.files) == 40

    def test_matches_rejects_malformed_section_two_count(self, watford_dfs_surface):
        """Section 2 keeps its own well-formed count byte: the low three bits
        (a file count is a multiple of 8) must be clear, as for section 1."""
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[768 + 5] = 0x0A  # bits 1,3 set -> 0x0A & 0x07 != 0, malformed
        assert not WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_title_uses_ten_chars_and_does_not_corrupt_files(self, tmp_path):
        """A Watford title is 10 chars: 8 in sector 0 (0x000) and 2 in sector
        1 (0x100), matching initialise. The file entries begin at sector 0
        byte 8, so the title must not reach there — setting a >8-char title
        once corrupted the first file. Regression: read/write used
        sector0[0:10], overlapping entry 0 and disagreeing with initialise.
        """
        from oaknut.dfs.dfs import DFS
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        names = ["ALPHA", "BRAVO", "CHARLIE"]
        image_filepath = tmp_path / "titled.ssd"
        with DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED, title="Old") as dfs:
            for name in names:
                (dfs.root / f"$.{name}").write_bytes(b"data")
            dfs.title = "JanFeb 84"  # 9 chars -> spills past sector 0 byte 8
        with DFS.from_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.title == "JanFeb 84"
            got = sorted(p.name for p in (dfs.root / "$").iterdir())
            assert got == sorted(names)  # no file corrupted by the title write

    def test_section_sequence_numbers_are_independent(self, tmp_path):
        """Each section keeps its own master sequence number (0x304 is "not a
        copy of 0x104"): adding files to section 2 increments section 2's
        number alone. Regression: the writer mirrored section 1's onto 2."""
        from oaknut.dfs.dfs import DFS
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        image_filepath = tmp_path / "seq.ssd"
        with DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED) as dfs:
            for i in range(35):  # 31 fill section 1, 4 spill into section 2
                (dfs.root / f"$.F{i:02d}").write_bytes(b"x")
        data = image_filepath.read_bytes()
        section1_seq = data[256 + 4]  # 0x104 — 31 increments
        section2_seq = data[768 + 4]  # 0x304 — 4 increments
        assert section1_seq != section2_seq

    @pytest.mark.parametrize("char_offset", [5, 6], ids=["length-bit-18", "start-sector-bit-10"])
    def test_matches_rejects_watford_extension_bits_in_file_entry(self, char_offset, tmp_path):
        """A file entry whose filename char 0x005 or 0x006 has its top bit set
        carries Watford's >256KB extension (length bit 18 / start-sector bit
        10, DiscImage.pdf p9). This reader handles only the <=256KB layout, so
        such an image is discounted rather than mis-read as standard Watford.
        """
        from oaknut.dfs.dfs import DFS
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        image_filepath = tmp_path / "ext.ssd"
        with DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED, title="Big") as dfs:
            (dfs.root / "$.DATA").write_bytes(b"x")

        spec = WATFORD_DFS_80T_SINGLE_SIDED.surface_specs[0]
        buffer = bytearray(image_filepath.read_bytes())
        surface = DiscImage(memoryview(buffer), [spec]).surface(0)
        assert WatfordDFSCatalogue.matches(surface)  # clean disc identifies

        # First section-1 entry sits at sector 0 offset 8; set the top bit of
        # the addressed filename character.
        buffer[8 + char_offset] |= 0x80
        assert not WatfordDFSCatalogue.matches(surface)

    def test_match_evidence_is_the_single_source_for_matches(self, watford_dfs_surface):
        """The boolean gate is derived from the evidence — one system, not two.
        A matched surface yields evidence; breaking a required signal removes
        both the evidence and the match, in lockstep."""
        assert WatfordDFSCatalogue.match_evidence(watford_dfs_surface) is not None
        assert WatfordDFSCatalogue.matches(watford_dfs_surface)

        buffer = watford_dfs_surface._disc_image.buffer
        buffer[512] = 0x00  # clobber the first byte of the 0xAA marker
        assert WatfordDFSCatalogue.match_evidence(watford_dfs_surface) is None
        assert not WatfordDFSCatalogue.matches(watford_dfs_surface)

    def test_untitled_disc_with_files_reports_empty_title(self, tmp_path):
        """An untitled Watford disc carrying files reports an empty title — not
        the file-entry bytes the old sector0[0:10] read leaked in."""
        from oaknut.dfs.dfs import DFS
        from oaknut.dfs.formats import WATFORD_DFS_80T_SINGLE_SIDED

        image_filepath = tmp_path / "untitled.ssd"
        with DFS.create_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED) as dfs:
            (dfs.root / "$.840101").write_bytes(b"data")  # name starts "84"
        with DFS.from_file(image_filepath, WATFORD_DFS_80T_SINGLE_SIDED) as dfs:
            assert dfs.title == ""

    def test_matches_rejects_too_few_sectors(self):
        """Test matches() rejects image with fewer than 4 sectors."""
        buffer = bytearray(768)  # Only 3 sectors
        spec = SurfaceSpec(
            num_tracks=1,
            sectors_per_track=3,
            bytes_per_sector=256,
            track_zero_offset_bytes=0,
            track_stride_bytes=768,
        )
        disc = DiscImage(memoryview(buffer), [spec])
        surface = disc.surface(0)

        assert not WatfordDFSCatalogue.matches(surface)


class TestWatfordDFSCatalogueGetDiskInfo:
    """Test reading disk info from Watford DFS catalogue."""

    def test_get_disk_info_empty_disk(self, watford_dfs_surface):
        """Test reading disk info from empty Watford DFS disk."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        disc_info = catalogue.get_disc_info()

        assert disc_info.title == "WATFORD"
        assert disc_info.num_files == 0  # Both sections empty
        assert disc_info.total_sectors == 800
        assert disc_info.boot_option == 0

    def test_get_disk_info_combines_file_counts(self, watford_dfs_surface):
        """Test that file count is sum of both catalog sections."""
        buffer = watford_dfs_surface._disc_image.buffer

        # Section 1: 5 files
        buffer[256 + 5] = 5 * 8

        # Section 2: 3 files
        buffer[768 + 5] = 3 * 8

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        disc_info = catalogue.get_disc_info()

        assert disc_info.num_files == 8  # 5 + 3


class TestWatfordDFSCatalogueListFiles:
    """Test listing files from Watford DFS catalogue."""

    def test_list_files_empty_catalog(self, watford_dfs_surface):
        """Test listing files from empty catalogue."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        files = catalogue.list_files()

        assert len(files) == 0

    def test_list_files_from_section_1(self, watford_dfs_surface):
        """Test listing files from section 1 only."""
        buffer = watford_dfs_surface._disc_image.buffer

        # Add one file to section 1
        buffer[8:15] = b"HELLO  "  # Filename
        buffer[15] = ord("$")  # Directory

        buffer[256 + 8 : 256 + 10] = b"\x00\x00"  # Load address low
        buffer[256 + 10 : 256 + 12] = b"\x00\x00"  # Exec address low
        buffer[256 + 12 : 256 + 14] = b"\x0a\x00"  # Length = 10 bytes
        buffer[256 + 14] = 0x00  # Extra byte
        buffer[256 + 15] = 0x04  # Start sector = 4

        buffer[256 + 5] = 1 * 8  # 1 file in section 1

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        files = catalogue.list_files()

        assert len(files) == 1
        assert files[0].filename == "HELLO"
        assert files[0].directory == "$"
        assert files[0].length == 10
        assert files[0].start_sector == 4


class TestWatfordDFSCatalogueValidation:
    """Test Watford DFS validation methods."""

    def test_validate_title_max_10_chars(self, watford_dfs_surface):
        """Test that titles are limited to 10 characters for Watford DFS."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # 10 chars should be OK
        catalogue.validate_title("TENCHARSS!")

        # 11 chars should fail
        with pytest.raises(ValueError, match="Title too long"):
            catalogue.validate_title("ELEVEN CHAR")

    def test_validate_empty_catalog(self, watford_dfs_surface):
        """Test validate() on empty catalog."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert len(errors) == 0

    def test_validate_detects_missing_aa_marker(self, watford_dfs_surface):
        """Test validate() detects missing 0xAA marker."""
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[512:524] = b"\x00" * 12  # Clear marker

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert any("marker" in str(err).lower() for err in errors)

    def test_validate_detects_metadata_mismatch(self, watford_dfs_surface):
        """Test validate() detects metadata synchronization issues."""
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[768 + 6] = 0xFF  # Mismatch boot option/sector count

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert any("mismatch" in str(err).lower() for err in errors)

    def test_validate_allows_independent_section_sequence_numbers(self, watford_dfs_surface):
        """Each section's master sequence number is independent — 0x304 is
        "not a copy of 0x104" (DiscImage.pdf p9) — so differing values are
        valid and must not be reported as a mismatch."""
        buffer = watford_dfs_surface._disc_image.buffer
        buffer[768 + 4] = (buffer[256 + 4] + 1) & 0xFF  # section-2 seq != section-1

        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        errors = catalogue.validate()

        assert not any("cycle" in str(err).lower() for err in errors)


class TestWatfordDFSCatalogueMaxFiles:
    """Test Watford DFS 62-file capacity."""

    def test_max_files_property(self, watford_dfs_surface):
        """Test that max_files returns 62."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        assert catalogue.max_files == 62


class TestWatfordDFSCatalogueFileOperations:
    """Test file operations that trigger write operations."""

    def test_add_file_entry(self, watford_dfs_surface):
        """Test adding a file entry (triggers _sync_metadata)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Add a file to section 1
        catalogue.add_file_entry(
            filename="TEST",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=4,
            locked=False,
        )

        # Verify file was added
        files = catalogue.list_files()
        assert len(files) == 1
        assert files[0].filename == "TEST"
        assert files[0].directory == "$"
        assert files[0].start_sector == 4

        # Verify disk info updated
        disc_info = catalogue.get_disc_info()
        assert disc_info.num_files == 1

    def test_remove_file_entry(self, watford_dfs_surface):
        """Test removing a file entry (triggers _rebuild_catalog)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Add a file first
        catalogue.add_file_entry(
            filename="TEST",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=100,
            start_sector=4,
            locked=False,
        )

        # Remove the file
        catalogue.remove_file_entry("$.TEST")

        # Verify file was removed
        files = catalogue.list_files()
        assert len(files) == 0

        disc_info = catalogue.get_disc_info()
        assert disc_info.num_files == 0

    def test_set_boot_option(self, watford_dfs_surface):
        """Test setting boot option (triggers _sync_metadata)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Set boot option to 3
        catalogue.set_boot_option(3)

        # Verify it was set
        disc_info = catalogue.get_disc_info()
        assert disc_info.boot_option == 3

    def test_compact(self, watford_dfs_surface):
        """Test compact operation (triggers _rebuild_catalog)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)

        # Add two files with a gap
        catalogue.add_file_entry(
            filename="FILE1",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=256,
            start_sector=4,
            locked=False,
        )
        catalogue.add_file_entry(
            filename="FILE2",
            directory="$",
            load_address=0x1900,
            exec_address=0x1900,
            length=256,
            start_sector=10,  # Gap from sector 5-9
            locked=False,
        )

        # Compact should work without errors
        catalogue.compact()

        # Verify files still exist
        files = catalogue.list_files()
        assert len(files) == 2

    def test_compact_with_order(self, watford_dfs_surface):
        """An explicit order positions the named file first (Watford layout)."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        catalogue.add_file_entry(
            filename="FILE1", directory="$", load_address=0, exec_address=0,
            length=256, start_sector=4, locked=False,
        )
        catalogue.add_file_entry(
            filename="FILE2", directory="$", load_address=0, exec_address=0,
            length=256, start_sector=5, locked=False,
        )

        catalogue.compact(order=["$.FILE2"])

        placed = sorted(catalogue.list_files(), key=lambda f: f.start_sector)
        # FILE2 first, in the lowest data sector (4, after the 0-3 catalogue).
        assert [f.path for f in placed] == ["$.FILE2", "$.FILE1"]
        assert placed[0].start_sector == 4

    def test_compact_preserves_attributes(self, watford_dfs_surface):
        """Compaction carries load/exec/lock across the two-section rebuild."""
        catalogue = WatfordDFSCatalogue(watford_dfs_surface)
        catalogue.add_file_entry(
            filename="KEEP", directory="$", load_address=0x1900, exec_address=0x8023,
            length=256, start_sector=4, locked=True,
        )
        catalogue.add_file_entry(
            filename="GAP", directory="$", load_address=0, exec_address=0,
            length=256, start_sector=10, locked=False,  # gap between 4 and 10
        )
        catalogue.remove_file_entry("$.GAP")

        catalogue.compact()

        keep = next(f for f in catalogue.list_files() if f.filename == "KEEP")
        assert keep.load_address == 0x1900
        assert keep.exec_address == 0x8023
        assert keep.locked is True
        assert keep.start_sector == 4  # moved down to fill the gap


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
