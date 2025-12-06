"""Metadata tests for reference disk images.

These tests verify disk-level metadata (titles, boot options, catalog structure)
matches the BBC BASIC generator specifications.
"""

import pytest


class TestDiskMetadata:
    """Verify disk titles, boot options, and catalog structure."""

    def test_basic_validation_title(self, reference_image):
        """Verify basic validation disk has title 'BASIC' (with null padding)."""
        disk = reference_image("01-basic-validation.ssd")
        # BBC BASIC *TITLE stores only first word before space
        assert disk.title.rstrip('\x00') == "BASIC"

    def test_catalog_sector_layout(self, reference_image):
        """Verify catalog occupies sectors 0-1, files start at sector 2+."""
        disk = reference_image("01-basic-validation.ssd")
        # All files should start at sector 2 or later (sectors 0-1 reserved for catalog)
        for file_entry in disk.files:
            assert file_entry.start_sector >= 2, (
                f"File {file_entry.path} starts at sector {file_entry.start_sector}, "
                "expected >= 2 (catalog occupies sectors 0-1)"
            )

    def test_disk_format_detection(self, reference_image):
        """Verify format detection works for all reference images."""
        # Should not raise exceptions
        disk_ssd_80t = reference_image("01-basic-validation.ssd")
        assert len(disk_ssd_80t.files) > 0

        disk_fragmented = reference_image("03-fragmented.ssd")
        assert len(disk_fragmented.files) > 0

        disk_dsd_side0 = reference_image("04-double-sided.dsd", side=0)
        assert len(disk_dsd_side0.files) > 0

        disk_dsd_side1 = reference_image("04-double-sided.dsd", side=1)
        assert len(disk_dsd_side1.files) > 0

    def test_80_track_format(self, reference_image):
        """Verify 80-track SSDs have correct capacity."""
        disk = reference_image("01-basic-validation.ssd")
        # 80 tracks × 10 sectors/track = 800 sectors total
        # Minus 2 for catalog = 798 sectors available
        info = disk.info
        assert info["total_sectors"] == 800

    def test_fragmented_disk_free_sectors(self, reference_image):
        """Verify fragmented disk reports correct free sectors."""
        disk = reference_image("03-fragmented.ssd")
        # 4 files remain after deletions (FILEA, FILEC, FILEE, MARKER)
        assert len(disk.files) == 4
        # Should have significant free space from deleted files
        assert disk.free_sectors > 0

    def test_double_sided_independent_metadata(self, reference_image):
        """Verify DSD sides have independent metadata."""
        disk0 = reference_image("04-double-sided.dsd", side=0)
        disk1 = reference_image("04-double-sided.dsd", side=1)

        # Independent file counts
        assert disk0.info["num_files"] == 13
        assert disk1.info["num_files"] == 9

        # Independent titles (may be different)
        # Just verify both have valid titles
        assert len(disk0.title.strip()) > 0
        assert len(disk1.title.strip()) > 0

    def test_catalog_capacity_edge_case(self, reference_image):
        """Verify edge cases disk fills catalog to exactly 31 files."""
        disk = reference_image("02-edge-cases.ssd")
        info = disk.info
        assert info["num_files"] == 31  # Maximum for Acorn DFS
        # Catalog should be reported as valid
        errors = disk.validate()
        assert len(errors) == 0, f"Catalog validation errors: {errors}"
