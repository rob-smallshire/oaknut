"""Tests for ADFS hard disc image support (.dat/.dsc pairs).

ADFS hard disc images consist of a .dat file (raw sector data) and a
.dsc sidecar file (22 bytes of SCSI disc geometry). The filesystem
structure is identical to floppy ADFS (old map, old directory).
"""

import pytest
from oaknut.adfs import ADFS
from oaknut.adfs.adfs import _hard_disc_format, _parse_dsc
from oaknut.adfs.exceptions import ADFSError

from tests.fixtures import BEEBEM_IMAGES_DIRPATH as IMAGES_DIR

# --- DSC parsing tests ---


class TestParseDSC:
    def test_parse_real_dsc(self):
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dsc_filepath.exists():
            pytest.skip("scsi0.dsc not available")
        geom = _parse_dsc(dsc_filepath)
        assert geom.cylinders == 306
        assert geom.heads == 4
        assert geom.sectors_per_track == 33

    def test_all_dsc_files_identical_geometry(self):
        """All test DSC files declare the same geometry."""
        for i in range(4):
            dsc_filepath = IMAGES_DIR / f"scsi{i}.dsc"
            if not dsc_filepath.exists():
                pytest.skip(f"scsi{i}.dsc not available")
            geom = _parse_dsc(dsc_filepath)
            assert geom.cylinders == 306
            assert geom.heads == 4

    def test_parse_dsc_wrong_size_raises(self, tmp_path):
        bad_dsc = tmp_path / "bad.dsc"
        bad_dsc.write_bytes(b"\x00" * 10)
        with pytest.raises(ADFSError, match="22 bytes"):
            _parse_dsc(bad_dsc)


class TestWriteDsc:
    """``write_dsc`` is the public counterpart of ``_parse_dsc``.

    Used by ``disc generate-dsc`` when no sidecar was shipped with the
    ``.dat`` (e.g. the RetroClinic Data Centre cfbackup images).
    """

    def test_round_trip(self, tmp_path):
        from oaknut.adfs import ADFSGeometry, write_dsc
        from oaknut.adfs.adfs import _parse_dsc

        dsc_filepath = tmp_path / "out.dsc"
        original = ADFSGeometry(cylinders=7935, heads=4, sectors_per_track=64)
        write_dsc(dsc_filepath, original)

        assert dsc_filepath.stat().st_size == 22
        parsed = _parse_dsc(dsc_filepath)
        assert parsed.cylinders == 7935
        assert parsed.heads == 4
        # _parse_dsc returns whatever SPT it has on the geometry default;
        # the field isn't stored in the 22-byte format, so we don't assert it.


# --- Hard disc format factory tests ---


class TestHardDiscFormat:
    def test_format_from_geometry(self):
        from oaknut.adfs.adfs import ADFSGeometry

        geom = ADFSGeometry(cylinders=306, heads=4)
        dat_size = 306 * 4 * 33 * 256  # Full size
        fmt = _hard_disc_format(geom, dat_size)
        # Single surface — ADFS uses linear LBA for hard discs
        assert len(fmt.surface_specs) == 1
        assert fmt.total_sectors == 306 * 4 * 33
        assert fmt.label == "HardDisc"

    def test_format_addressable_extent_matches_file(self):
        """Addressable surface covers every sector in the file.

        ADFS uses linear LBA, so the surface must address all
        ``dat_size_bytes / 256`` sectors regardless of how the geometry
        groups them into cylinders.
        """
        from oaknut.adfs.adfs import ADFSGeometry

        geom = ADFSGeometry(cylinders=10, heads=2)
        dat_size = 10 * 2 * 33 * 256
        fmt = _hard_disc_format(geom, dat_size)
        spec = fmt.surface_specs[0]
        assert spec.bytes_per_sector == 256
        assert spec.num_tracks * spec.sectors_per_track == dat_size // 256

    def test_format_addressable_extent_when_geometry_doesnt_divide(self):
        """Truncated/partial files (e.g. cfbackup .dat with no .dsc tail)
        keep their full sector range addressable even when the file size
        isn't a whole number of cylinders for the supplied geometry."""
        from oaknut.adfs.adfs import ADFSGeometry

        # 10,520 sectors is not a multiple of 4 × 64 = 256.  The file
        # nonetheless contains 10,520 valid sectors and they must all
        # be reachable.  Regression for the cf1gb_v102.dat truncation
        # bug — the old cylinder-shaped surface dropped 92 trailing
        # sectors and made directories living there unreadable.
        geom = ADFSGeometry(cylinders=7935, heads=4, sectors_per_track=64)
        dat_size = 10520 * 256
        fmt = _hard_disc_format(geom, dat_size)
        spec = fmt.surface_specs[0]
        assert spec.num_tracks * spec.sectors_per_track == 10520
        assert fmt.total_sectors == 10520

    def test_format_addressable_when_dsc_loses_spt(self):
        """``_parse_dsc`` always returns the default SPT (33) since the
        22-byte sidecar doesn't carry an SPT field.  The surface must
        still match the file even when the parsed geometry's SPT is
        wrong relative to what the file was created with."""
        from oaknut.adfs.adfs import ADFSGeometry

        # Simulate the parsed geometry: cylinders/heads from the file,
        # SPT defaulted to 33 by ADFSGeometry's default.
        parsed_geom = ADFSGeometry(cylinders=7935, heads=4)
        assert parsed_geom.sectors_per_track == 33
        dat_size = 10520 * 256
        fmt = _hard_disc_format(parsed_geom, dat_size)
        assert fmt.surface_specs[0].num_tracks * fmt.surface_specs[0].sectors_per_track == 10520

    def test_format_not_multiple_of_sector_raises(self):
        from oaknut.adfs.adfs import ADFSGeometry

        geom = ADFSGeometry(cylinders=10, heads=1)
        with pytest.raises(ADFSError):
            _hard_disc_format(geom, 1000)  # Not a multiple of 256


# --- Opening hard disc images via from_file ---


class TestADFSHardDiscFromFile:
    def test_open_via_dat(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs:
            assert adfs.root.is_dir()
            assert adfs.root.exists()

    def test_open_via_dsc(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dsc_filepath) as adfs:
            assert adfs.root.is_dir()

    def test_dat_and_dsc_give_same_result(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs_dat:
            with ADFS.from_file(dsc_filepath) as adfs_dsc:
                assert adfs_dat.title == adfs_dsc.title
                dat_entries = [e.name for e in adfs_dat.root]
                dsc_entries = [e.name for e in adfs_dsc.root]
                assert dat_entries == dsc_entries

    def test_scsi0_root_entries(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs:
            entries = list(adfs.root)
            names = [e.name for e in entries]
            assert "DOS" in names
            assert "DOSBOOT" in names or any(not e.is_dir() for e in entries)

    def test_scsi0_has_subdirectories(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs:
            dirs = [e for e in adfs.root if e.is_dir()]
            assert len(dirs) >= 1

    def test_scsi0_walk(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs:
            results = list(adfs.root.walk())
            # At least root + subdirectories
            assert len(results) >= 2

    def test_scsi0_read_file(self):
        dat_filepath = IMAGES_DIR / "scsi0.dat"
        dsc_filepath = IMAGES_DIR / "scsi0.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip("scsi0.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs:
            # Read the first non-directory entry
            for entry in adfs.root:
                if entry.is_file():
                    data = entry.read_bytes()
                    assert len(data) == entry.stat().length
                    break


class TestADFSHardDiscSmallImages:
    """Test with scsi1-3 which are minimal images (94 sectors)."""

    @pytest.mark.parametrize("index", [1, 2, 3])
    def test_open_small_image(self, index):
        dat_filepath = IMAGES_DIR / f"scsi{index}.dat"
        dsc_filepath = IMAGES_DIR / f"scsi{index}.dsc"
        if not dat_filepath.exists() or not dsc_filepath.exists():
            pytest.skip(f"scsi{index}.dat/.dsc not available")

        with ADFS.from_file(dat_filepath) as adfs:
            assert adfs.root.is_dir()
            # Root should be readable even on a near-empty disc
            list(adfs.root)


# --- Missing companion file ---


class TestADFSHardDiscMissingCompanion:
    def test_dat_without_dsc_reads_by_content(self, tmp_path):
        # A .dsc is no longer required: New Map hard discs carry their geometry
        # in the disc record, so a .dat without a sidecar is read by content.
        # An image that is not valid ADFS raises an ADFS error, not a missing-
        # sidecar error.
        from oaknut.adfs.exceptions import ADFSError

        dat_filepath = tmp_path / "test.dat"
        dat_filepath.write_bytes(b"\x00" * 1024)
        with pytest.raises(ADFSError):
            with ADFS.from_file(dat_filepath):
                pass

    def test_dsc_without_dat_raises(self, tmp_path):
        dsc_filepath = tmp_path / "test.dsc"
        dsc_filepath.write_bytes(b"\x00" * 22)
        with pytest.raises(FileNotFoundError, match=r"\.dat"):
            with ADFS.from_file(dsc_filepath):
                pass


# --- from_buffer with non-floppy size ---


class TestADFSHardDiscFromBuffer:
    def test_non_floppy_size_accepted(self):
        """A buffer larger than any floppy format should be accepted if valid ADFS."""
        from helpers.adfs_image import make_old_directory, make_old_free_space_map

        total_sectors = 4096
        buf = bytearray(total_sectors * 256)

        fsm = make_old_free_space_map([(7, total_sectors - 7)], disc_size_sectors=total_sectors)
        buf[0:512] = fsm

        root_dir = make_old_directory([], dir_name="$", title="HardDisc")
        buf[0x200 : 0x200 + 1280] = root_dir

        adfs = ADFS.from_buffer(memoryview(buf))
        assert adfs.title == "HardDisc"
        assert list(adfs.root) == []
