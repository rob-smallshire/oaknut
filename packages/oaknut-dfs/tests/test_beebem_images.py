"""Integration tests against real BeebEm disc images.

These tests validate parsing against genuine disc images from BeebEm,
covering both DFS (SSD/DSD) and ADFS (ADL) formats.
"""

from pathlib import Path

import pytest

from oaknut_dfs.adfs import ADFS
from oaknut_dfs.dfs import DFS
from oaknut_dfs.formats import DiskFormat
from oaknut_dfs.surface import SurfaceSpec


IMAGES_DIR = Path(__file__).parent / "images"


def _ssd_format(size: int) -> DiskFormat:
    """Create a DiskFormat for an SSD image of any size."""
    sectors_per_track = 10
    bytes_per_sector = 256
    track_size = sectors_per_track * bytes_per_sector
    num_tracks = size // track_size
    return DiskFormat(
        surface_specs=[
            SurfaceSpec(
                num_tracks=num_tracks,
                sectors_per_track=sectors_per_track,
                bytes_per_sector=bytes_per_sector,
                track_zero_offset_bytes=0,
                track_stride_bytes=track_size,
            )
        ],
        catalogue_name="acorn-dfs",
    )


def _dsd_format(size: int) -> DiskFormat:
    """Create a DiskFormat for an interleaved DSD image of any size."""
    sectors_per_track = 10
    bytes_per_sector = 256
    track_size = sectors_per_track * bytes_per_sector
    num_tracks = size // (2 * track_size)
    return DiskFormat(
        surface_specs=[
            SurfaceSpec(
                num_tracks=num_tracks,
                sectors_per_track=sectors_per_track,
                bytes_per_sector=bytes_per_sector,
                track_zero_offset_bytes=0,
                track_stride_bytes=2 * track_size,
            ),
            SurfaceSpec(
                num_tracks=num_tracks,
                sectors_per_track=sectors_per_track,
                bytes_per_sector=bytes_per_sector,
                track_zero_offset_bytes=track_size,
                track_stride_bytes=2 * track_size,
            ),
        ],
        catalogue_name="acorn-dfs",
    )


# --- DFS SSD images ---


class TestWelcomeSSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "Welcome.ssd"
        if not filepath.exists():
            pytest.skip("Welcome.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_title(self, dfs):
        assert dfs.title.strip() == "WELCOME-DISK"

    def test_has_files(self, dfs):
        assert len(dfs.files) > 0

    def test_walk(self, dfs):
        results = list(dfs.root.walk())
        assert len(results) >= 1  # At least root
        total_files = sum(len(files) for _, _, files in results)
        assert total_files == len(dfs.files)


class TestEconetLevel1SSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "econet_level_1_utils.ssd"
        if not filepath.exists():
            pytest.skip("econet_level_1_utils.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_title(self, dfs):
        assert "Level 1" in dfs.title

    def test_file_count(self, dfs):
        assert len(dfs.files) == 13

    def test_all_files_readable(self, dfs):
        for entry in dfs.root / "$":
            data = entry.read_bytes()
            assert len(data) == entry.stat().length


class TestEconetLevel2SSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "econet_level_2_utils.ssd"
        if not filepath.exists():
            pytest.skip("econet_level_2_utils.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_title(self, dfs):
        assert "Level 2" in dfs.title

    def test_file_count(self, dfs):
        assert len(dfs.files) == 5


class TestMusic500SSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "Music500.ssd"
        if not filepath.exists():
            pytest.skip("Music500.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_title(self, dfs):
        assert "MUSIC" in dfs.title

    def test_file_count(self, dfs):
        assert len(dfs.files) == 14

    def test_all_files_readable(self, dfs):
        for entry in dfs.root / "$":
            data = entry.read_bytes()
            assert len(data) == entry.stat().length


class TestGamesSSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "Games.ssd"
        if not filepath.exists():
            pytest.skip("Games.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_has_files(self, dfs):
        assert len(dfs.files) > 0

    def test_all_files_readable(self, dfs):
        for entry in dfs.root / "$":
            data = entry.read_bytes()
            assert len(data) == entry.stat().length


class TestM5000SSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "M5000-4.ssd"
        if not filepath.exists():
            pytest.skip("M5000-4.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_has_files(self, dfs):
        assert len(dfs.files) > 0


class TestTestSSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "Test.ssd"
        if not filepath.exists():
            pytest.skip("Test.ssd not available")
        fmt = _ssd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_opens(self, dfs):
        # Minimal image — just verify it opens
        assert dfs.title is not None


# --- DFS DSD images ---


class TestCPMUtilitiesDSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "CPM_Utilities_Disc.dsd"
        if not filepath.exists():
            pytest.skip("CPM_Utilities_Disc.dsd not available")
        fmt = _dsd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_title(self, dfs):
        assert "CP/M" in dfs.title

    def test_has_files(self, dfs):
        assert len(dfs.files) >= 1


class TestL3UtilsDSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "L3-Utils.dsd"
        if not filepath.exists():
            pytest.skip("L3-Utils.dsd not available")
        fmt = _dsd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_file_count(self, dfs):
        assert len(dfs.files) == 25

    def test_all_files_readable(self, dfs):
        for f in dfs.files:
            data = dfs.path(f.path).read_bytes()
            assert len(data) == f.length


class TestTorchHardDiscUtilsDSD:
    """Torch hard disc utils — non-standard DFS variant.

    The catalogue references sectors beyond side 0 bounds, so file
    data cannot be fully read with standard Acorn DFS assumptions.
    """

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "Torch_hard_disc_utils.dsd"
        if not filepath.exists():
            pytest.skip("Torch_hard_disc_utils.dsd not available")
        fmt = _dsd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_has_files(self, dfs):
        assert len(dfs.files) > 0


class TestTorchStandardUtilities2DSD:

    @pytest.fixture
    def dfs(self):
        filepath = IMAGES_DIR / "Torch_standard_utilities_2.dsd"
        if not filepath.exists():
            pytest.skip("Torch_standard_utilities_2.dsd not available")
        fmt = _dsd_format(filepath.stat().st_size)
        with DFS.from_file(filepath, fmt) as dfs:
            yield dfs

    def test_has_files(self, dfs):
        assert len(dfs.files) > 0


# --- ADFS ADL images ---


class TestMasterWelcomeADL:

    @pytest.fixture
    def adfs(self):
        filepath = IMAGES_DIR / "MasterWelcome.adl"
        if not filepath.exists():
            pytest.skip("MasterWelcome.adl not available")
        with ADFS.from_file(filepath) as adfs:
            yield adfs

    def test_title(self, adfs):
        assert adfs.title == "80T Welcome & Utils"

    def test_boot_option(self, adfs):
        assert adfs.boot_option == 3

    def test_total_size(self, adfs):
        assert adfs.total_size == 655360

    def test_root_has_files_and_dirs(self, adfs):
        entries = list(adfs.root)
        names = [e.name for e in entries]
        assert "!Boot" in names
        assert "HELP" in names
        assert "LIBRARY" in names

    def test_walk_file_count(self, adfs):
        total = sum(len(fn) for _, _, fn in adfs.root.walk())
        assert total == 73

    def test_subdirectory_readable(self, adfs):
        help_dir = adfs.root / "HELP"
        assert help_dir.is_dir()
        entries = list(help_dir)
        assert len(entries) == 9

    def test_all_files_readable(self, adfs):
        for dirpath, _, filenames in adfs.root.walk():
            for name in filenames:
                p = dirpath / name
                data = p.read_bytes()
                assert len(data) == p.stat().length


class TestL3ServerADL:

    @pytest.fixture
    def adfs(self):
        filepath = IMAGES_DIR / "l3server.adl"
        if not filepath.exists():
            pytest.skip("l3server.adl not available")
        with ADFS.from_file(filepath) as adfs:
            yield adfs

    def test_total_size(self, adfs):
        assert adfs.total_size == 655360

    def test_file_count(self, adfs):
        total = sum(len(fn) for _, _, fn in adfs.root.walk())
        assert total == 15

    def test_all_files_readable(self, adfs):
        for dirpath, _, filenames in adfs.root.walk():
            for name in filenames:
                p = dirpath / name
                data = p.read_bytes()
                assert len(data) == p.stat().length


class TestBBCMaster512ADL:

    @pytest.fixture
    def adfs(self):
        filepath = IMAGES_DIR / "BBCMaster512-Disc1-DosPlusBoot.adl"
        if not filepath.exists():
            pytest.skip("BBCMaster512-Disc1-DosPlusBoot.adl not available")
        with ADFS.from_file(filepath) as adfs:
            yield adfs

    def test_title(self, adfs):
        assert adfs.title == "Acorn DOS Boot Disc"

    def test_file_count(self, adfs):
        total = sum(len(fn) for _, _, fn in adfs.root.walk())
        assert total == 1


class TestL3FSISW_ADL:

    @pytest.fixture
    def adfs(self):
        filepath = IMAGES_DIR / "L3FS-ISW.adl"
        if not filepath.exists():
            pytest.skip("L3FS-ISW.adl not available")
        with ADFS.from_file(filepath) as adfs:
            yield adfs

    def test_title(self, adfs):
        assert "L3FS" in adfs.title

    def test_has_subdirectories(self, adfs):
        root_entries = list(adfs.root)
        dirs = [e for e in root_entries if e.is_dir()]
        assert len(dirs) == 3

    def test_walk_file_count(self, adfs):
        total = sum(len(fn) for _, _, fn in adfs.root.walk())
        assert total == 57

    def test_all_files_readable(self, adfs):
        for dirpath, _, filenames in adfs.root.walk():
            for name in filenames:
                p = dirpath / name
                data = p.read_bytes()
                assert len(data) == p.stat().length
