"""Integration tests for DFS Filesystem Layer 4.

These tests verify end-to-end functionality across multiple operations,
including round-trip persistence, real-world workflows, and cross-layer integration.
"""

import pytest
from pathlib import Path

from oaknut_dfs.dfs_filesystem import DFSImage, BootOption
from oaknut_dfs.exceptions import CatalogFullError, DiskFullError, FileLocked, InvalidFormatError


# ========== Fixtures ==========


@pytest.fixture
def fragmented_disk(tmp_path):
    """Disk with fragmentation for compact testing."""
    path = tmp_path / "frag.ssd"
    with DFSImage.create(path, title="FRAG") as disk:
        disk.save("$.FILE1", b"x" * 1000)
        disk.save("$.FILE2", b"y" * 2000)
        disk.save("$.FILE3", b"z" * 1500)
        disk.delete("$.FILE2")  # Creates gap
    return path


# ========== Round-trip tests ==========


class TestRoundTrip:
    """Test full create → save → close → reopen → verify cycles."""

    def test_roundtrip_create_save_reopen(self, tmp_path):
        """Create disk, save file, close, reopen, verify."""
        path = tmp_path / "test.ssd"

        # Create and save
        with DFSImage.create(path, title="ROUNDTRIP") as disk:
            disk.save("$.TEST", b"test data", load_address=0x1900, exec_address=0x8023)

        # Reopen and verify
        with DFSImage.open(path) as disk:
            assert disk.title == "ROUNDTRIP"
            assert disk.exists("$.TEST")
            assert disk.load("$.TEST") == b"test data"
            info = disk.get_file_info("$.TEST")
            assert info.load_address == 0x1900
            assert info.exec_address == 0x8023

    def test_roundtrip_multiple_files(self, tmp_path):
        """Save multiple files, reopen, verify all."""
        path = tmp_path / "test.ssd"

        # Create with multiple files
        with DFSImage.create(path, title="MULTI") as disk:
            disk.save("$.FILE1", b"data1")
            disk.save("$.FILE2", b"data2")
            disk.save("A.FILE3", b"data3")

        # Reopen and verify
        with DFSImage.open(path) as disk:
            assert len(disk.files) == 3
            assert disk.load("$.FILE1") == b"data1"
            assert disk.load("$.FILE2") == b"data2"
            assert disk.load("A.FILE3") == b"data3"

    def test_roundtrip_modifications(self, tmp_path):
        """Create, modify, reopen, verify changes persisted."""
        path = tmp_path / "test.ssd"

        # Create initial files
        with DFSImage.create(path, title="MODIFY") as disk:
            disk.save("$.FILE1", b"original1")
            disk.save("$.FILE2", b"original2")

        # Modify files
        with DFSImage.open(path) as disk:
            disk.delete("$.FILE1")
            disk.save("$.FILE3", b"new3")
            disk.title = "MODIFIED"

        # Verify modifications
        with DFSImage.open(path) as disk:
            assert disk.title == "MODIFIED"
            assert not disk.exists("$.FILE1")
            assert disk.exists("$.FILE2")
            assert disk.exists("$.FILE3")
            assert disk.load("$.FILE3") == b"new3"

    def test_roundtrip_locked_files(self, tmp_path):
        """Locked files persist across sessions."""
        path = tmp_path / "test.ssd"

        # Create locked file
        with DFSImage.create(path, title="LOCKED") as disk:
            disk.save("$.FILE", b"protected", locked=True)

        # Verify locked status persists
        with DFSImage.open(path) as disk:
            info = disk.get_file_info("$.FILE")
            assert info.locked is True

            # Locked file still protects
            with pytest.raises(FileLocked):
                disk.delete("$.FILE")

    def test_roundtrip_boot_option(self, tmp_path):
        """Boot option persists across sessions."""
        path = tmp_path / "test.ssd"

        # Set boot option
        with DFSImage.create(path, title="BOOT") as disk:
            disk.boot_option = BootOption.RUN

        # Verify persistence
        with DFSImage.open(path) as disk:
            assert disk.boot_option == BootOption.RUN

    def test_roundtrip_large_file(self, tmp_path):
        """Large files persist correctly."""
        path = tmp_path / "test.ssd"
        large_data = b"X" * 50000  # ~50KB

        # Save large file
        with DFSImage.create(path, title="LARGE") as disk:
            disk.save("$.LARGE", large_data)

        # Verify
        with DFSImage.open(path) as disk:
            loaded = disk.load("$.LARGE")
            assert loaded == large_data


# ========== Real-world workflows ==========


class TestRealWorldWorkflows:
    """Test realistic usage scenarios."""

    def test_game_disk_workflow(self, tmp_path):
        """Create a typical game disk with boot file."""
        path = tmp_path / "game.ssd"

        with DFSImage.create(path, title="MY GAME") as disk:
            # Set boot option
            disk.boot_option = BootOption.RUN

            # Create boot file
            disk.save("$.!BOOT", b"*RUN $.MAIN\r")

            # Add game files
            disk.save("$.MAIN", b"game code" * 1000, load_address=0x1900, exec_address=0x1900)
            disk.save("$.DATA", b"game data" * 500)
            disk.save("$.SCORES", b"high scores")

        # Verify game disk
        with DFSImage.open(path) as disk:
            assert disk.title == "MY GAME"
            assert disk.boot_option == BootOption.RUN
            assert disk.exists("$.!BOOT")
            assert disk.exists("$.MAIN")
            assert len(disk.files) == 4

    def test_backup_restore_workflow(self, tmp_path):
        """Export all files, create new disk, restore."""
        original = tmp_path / "original.ssd"
        backup_dir = tmp_path / "backup"
        restored = tmp_path / "restored.ssd"

        # Create original disk
        with DFSImage.create(original, title="ORIGINAL") as disk:
            disk.save("$.FILE1", b"data1", load_address=0x1900)
            disk.save("$.FILE2", b"data2", locked=True)
            disk.save("A.FILE3", b"data3")

        # Export all files
        with DFSImage.open(original) as disk:
            disk.export_all(backup_dir)

        # Restore to new disk
        with DFSImage.create(restored, title="RESTORED") as disk:
            for inf_file in backup_dir.glob("*.inf"):
                data_file = inf_file.with_suffix("")
                if data_file.exists():
                    disk.import_from_inf(data_file)

        # Verify restoration
        with DFSImage.open(restored) as disk:
            assert len(disk.files) == 3
            assert disk.load("$.FILE1") == b"data1"
            assert disk.load("$.FILE2") == b"data2"
            assert disk.load("A.FILE3") == b"data3"

            # Verify metadata preserved
            info1 = disk.get_file_info("$.FILE1")
            assert info1.load_address == 0x1900

            info2 = disk.get_file_info("$.FILE2")
            assert info2.locked is True

    def test_compact_workflow(self, tmp_path, fragmented_disk):
        """Typical compaction workflow."""
        # Open fragmented disk
        with DFSImage.open(fragmented_disk) as disk:
            # Check fragmentation
            free_map_before = disk.get_free_map()
            assert len(free_map_before) > 1  # Has gaps

            # Compact
            files_moved = disk.compact()
            assert files_moved > 0

            # Verify no fragmentation
            free_map_after = disk.get_free_map()
            assert len(free_map_after) == 1

            # Verify files intact
            assert disk.load("$.FILE1") == b"x" * 1000
            assert disk.load("$.FILE3") == b"z" * 1500

    def test_incremental_development_workflow(self, tmp_path):
        """Iteratively add files like during development."""
        path = tmp_path / "dev.ssd"

        # Session 1: Initial files
        with DFSImage.create(path, title="DEV") as disk:
            disk.save("$.MAIN", b"version 1")

        # Session 2: Add more files
        with DFSImage.open(path) as disk:
            disk.save("$.DATA", b"config")
            disk.save("$.UTILS", b"helpers")

        # Session 3: Replace main
        with DFSImage.open(path) as disk:
            disk.delete("$.MAIN")
            disk.save("$.MAIN", b"version 2")

        # Verify final state
        with DFSImage.open(path) as disk:
            assert disk.load("$.MAIN") == b"version 2"
            assert len(disk.files) == 3


# ========== Edge cases ==========


class TestEdgeCases:
    """Test boundary conditions and edge cases."""

    def test_empty_disk_operations(self, tmp_path):
        """Operations on empty disk."""
        path = tmp_path / "empty.ssd"

        with DFSImage.create(path, title="EMPTY") as disk:
            assert len(disk.files) == 0
            assert disk.free_sectors == 398
            assert disk.validate() == []
            assert disk.get_free_map() == [(2, 398)]

            # Iteration over empty disk
            count = sum(1 for _ in disk)
            assert count == 0

    def test_full_disk_behavior(self, tmp_path):
        """Behavior when disk is nearly full."""
        path = tmp_path / "full.ssd"

        with DFSImage.create(path, title="FULL") as disk:
            # Fill disk almost completely
            large_data = b"X" * (397 * 256)  # Leave 1 sector free
            disk.save("$.LARGE", large_data)

            # Should have very little space left
            assert disk.free_sectors == 1

            # Adding tiny file should still work
            disk.save("$.TINY", b"small")
            assert disk.exists("$.TINY")

    def test_max_files_catalog(self, tmp_path):
        """Create disk with maximum files (31)."""
        path = tmp_path / "maxfiles.ssd"

        with DFSImage.create(path, title="MAX") as disk:
            # Add 31 files (max for DFS)
            for i in range(31):
                disk.save(f"$.F{i:02d}", b"data")

            assert len(disk.files) == 31

            # 32nd file should raise
            with pytest.raises(CatalogFullError, match="full"):
                disk.save("$.F32", b"data")

    def test_filename_edge_cases(self, tmp_path):
        """Test filename boundary conditions."""
        path = tmp_path / "names.ssd"

        with DFSImage.create(path, title="NAMES") as disk:
            # 7-character filename (max)
            disk.save("$.ABCDEFG", b"max length name")
            assert disk.exists("$.ABCDEFG")

            # Special characters
            disk.save("$.!BOOT", b"boot")
            disk.save("$.TEST-1", b"dash")
            disk.save("$.FILE_2", b"underscore")

            assert disk.exists("$.!BOOT")
            assert disk.exists("$.TEST-1")
            assert disk.exists("$.FILE_2")

    def test_zero_length_file(self, tmp_path):
        """Save and load zero-length file."""
        path = tmp_path / "zero.ssd"

        with DFSImage.create(path, title="ZERO") as disk:
            disk.save("$.EMPTY", b"")
            assert disk.exists("$.EMPTY")
            assert disk.load("$.EMPTY") == b""


# ========== Cross-layer integration ==========


class TestCrossLayerIntegration:
    """Test interactions between Layer 4 and lower layers."""

    def test_layer3_catalog_consistency(self, tmp_path):
        """Verify Layer 4 keeps Layer 3 catalog consistent."""
        path = tmp_path / "catalog.ssd"

        with DFSImage.create(path, title="CATALOG") as disk:
            disk.save("$.FILE1", b"data1")
            disk.save("$.FILE2", b"data2")

            # Access Layer 3 catalog directly
            catalog_info = disk._catalog.read_disk_info()
            assert catalog_info.num_files == 2
            assert catalog_info.title == "CATALOG"

            catalog_files = disk._catalog.list_files()
            assert len(catalog_files) == 2

    def test_layer2_sector_access(self, tmp_path):
        """Verify Layer 4 writes sectors correctly through Layer 2."""
        path = tmp_path / "sectors.ssd"

        with DFSImage.create(path, title="SECTORS") as disk:
            disk.save("$.FILE", b"X" * 512)  # 2 sectors

            # Access Layer 2 sector image
            sector_image = disk._catalog._sector_image

            # File should start at sector 2
            sector2 = sector_image.read_sector(2)
            sector3 = sector_image.read_sector(3)

            assert sector2 == b"X" * 256
            assert sector3 == b"X" * 256

    def test_layer1_disk_image_persistence(self, tmp_path):
        """Verify changes persist to Layer 1 disk image."""
        path = tmp_path / "persist.ssd"

        # Create and modify
        with DFSImage.create(path, title="PERSIST") as disk:
            disk.save("$.FILE", b"persistent data")

        # Verify file was written to disk
        assert path.exists()
        file_size = path.stat().st_size
        assert file_size == 40 * 10 * 256  # 40 tracks, 10 sectors/track, 256 bytes/sector

        # Raw file should contain our data
        raw_data = path.read_bytes()
        assert b"persistent data" in raw_data


# ========== Error handling ==========


class TestErrorHandling:
    """Test error messages and exception handling."""

    def test_file_not_found_error_message(self, tmp_path):
        """FileNotFoundError includes helpful info."""
        path = tmp_path / "test.ssd"

        with DFSImage.create(path, title="TEST") as disk:
            with pytest.raises(FileNotFoundError, match="MISSING"):
                disk.load("$.MISSING")

    def test_disk_full_error_message(self, tmp_path):
        """Disk full error is clear."""
        path = tmp_path / "test.ssd"

        with DFSImage.create(path, title="TEST") as disk:
            # Try to save file larger than available space
            large_data = b"X" * (399 * 256)  # More than 398 available sectors
            with pytest.raises(DiskFullError, match="free"):
                disk.save("$.LARGE", large_data)

    def test_locked_file_error_messages(self, tmp_path):
        """Locked file operations give clear errors."""
        path = tmp_path / "test.ssd"

        with DFSImage.create(path, title="TEST") as disk:
            disk.save("$.LOCKED", b"data", locked=True)

            # Delete locked file
            with pytest.raises(FileLocked, match="locked"):
                disk.delete("$.LOCKED")

            # Rename locked file
            with pytest.raises(FileLocked, match="locked"):
                disk.rename("$.LOCKED", "$.RENAMED")

    def test_invalid_format_error(self, tmp_path):
        """Opening invalid disk gives clear error."""
        invalid = tmp_path / "invalid.ssd"
        invalid.write_bytes(b"not a disk image" * 100)

        with pytest.raises(InvalidFormatError, match="size"):
            DFSImage.open(invalid)


# ========== Consistency checks ==========


class TestConsistency:
    """Test internal consistency after operations."""

    def test_free_space_consistency(self, tmp_path):
        """Free space calculations remain consistent."""
        path = tmp_path / "test.ssd"

        with DFSImage.create(path, title="TEST") as disk:
            initial_free = disk.free_sectors

            # Save file
            disk.save("$.FILE", b"X" * 512)  # 2 sectors
            assert disk.free_sectors == initial_free - 2

            # Delete file
            disk.delete("$.FILE")
            assert disk.free_sectors == initial_free

    def test_file_count_consistency(self, tmp_path):
        """File count stays consistent with operations."""
        path = tmp_path / "test.ssd"

        with DFSImage.create(path, title="TEST") as disk:
            assert len(disk) == 0

            disk.save("$.FILE1", b"data1")
            assert len(disk) == 1

            disk.save("$.FILE2", b"data2")
            assert len(disk) == 2

            disk.delete("$.FILE1")
            assert len(disk) == 1

            disk.rename("$.FILE2", "$.FILE3")
            assert len(disk) == 1

    def test_validation_consistency(self, tmp_path):
        """Validation passes after all operations."""
        path = tmp_path / "test.ssd"

        with DFSImage.create(path, title="TEST") as disk:
            # Initial validation
            assert disk.validate() == []

            # After saves
            disk.save("$.FILE1", b"data1")
            disk.save("$.FILE2", b"data2")
            assert disk.validate() == []

            # After delete
            disk.delete("$.FILE1")
            assert disk.validate() == []

            # After rename
            disk.rename("$.FILE2", "$.FILE3")
            assert disk.validate() == []
