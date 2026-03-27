"""Parameterised tests for real-world game disc images.

These tests exercise oaknut-dfs against commercially released BBC Micro
game discs, validating read-only operations (catalogue parsing, file
loading, metadata inspection, validation) without modifying the originals.
"""

import pytest
from pathlib import Path

import oaknut_dfs.acorn_dfs_catalogue  # noqa: F401

from oaknut_dfs import DFS
from oaknut_dfs.formats import ACORN_DFS_80T_SINGLE_SIDED


GAMES_DIRPATH = Path(__file__).parent / "data" / "images" / "games"

GAME_IMAGES = sorted(GAMES_DIRPATH.glob("*.ssd"))

GAME_IDS = [p.stem for p in GAME_IMAGES]


@pytest.fixture(params=GAME_IMAGES, ids=GAME_IDS)
def game_disc(request) -> DFS:
    """Load a game disc image read-only (from an immutable bytes copy)."""
    image_filepath = request.param
    # Use bytes (immutable) to guarantee we cannot modify the original
    buffer = bytearray(image_filepath.read_bytes())
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_80T_SINGLE_SIDED)


class TestGameDiscCatalogue:
    """Verify catalogue can be read from each game disc."""

    def test_has_files(self, game_disc):
        """Disc contains at least one file."""
        assert len(game_disc.files) > 0

    def test_file_count_within_limits(self, game_disc):
        """File count is within Acorn DFS maximum of 31."""
        assert 0 < len(game_disc.files) <= 31

    def test_title_is_string(self, game_disc):
        """Disc title is a non-empty string (ignoring null padding)."""
        title = game_disc.title.rstrip("\x00").strip()
        assert len(title) > 0

    def test_title_within_max_length(self, game_disc):
        """Disc title does not exceed 12 characters."""
        assert len(game_disc.title) <= 12

    def test_boot_option_valid(self, game_disc):
        """Boot option is in the range 0-3."""
        assert game_disc.boot_option in (0, 1, 2, 3)

    def test_total_sectors_positive(self, game_disc):
        """Total sector count is positive and consistent with 80-track format."""
        info = game_disc.info
        assert info["total_sectors"] == 800  # 80 tracks * 10 sectors


class TestGameDiscFileEntries:
    """Verify file entry metadata is well-formed for each game disc."""

    def test_all_filenames_valid(self, game_disc):
        """Every filename is 1-7 characters."""
        for entry in game_disc.files:
            assert 1 <= len(entry.filename) <= 7, (
                f"Filename {entry.filename!r} has invalid length {len(entry.filename)}"
            )

    def test_all_directories_single_char(self, game_disc):
        """Every directory is a single character."""
        for entry in game_disc.files:
            assert len(entry.directory) == 1, (
                f"Directory {entry.directory!r} for {entry.path} is not a single character"
            )

    def test_all_start_sectors_after_catalogue(self, game_disc):
        """Every file starts at sector 2 or later (sectors 0-1 are catalogue)."""
        for entry in game_disc.files:
            assert entry.start_sector >= 2, (
                f"File {entry.path} starts at sector {entry.start_sector}, expected >= 2"
            )

    def test_all_lengths_non_negative(self, game_disc):
        """Every file has a non-negative length."""
        for entry in game_disc.files:
            assert entry.length >= 0, (
                f"File {entry.path} has negative length {entry.length}"
            )

    def test_all_paths_well_formed(self, game_disc):
        """Every file path is in the form D.FILENAME."""
        for entry in game_disc.files:
            assert "." in entry.path
            directory, filename = entry.path.split(".", 1)
            assert len(directory) == 1
            assert len(filename) >= 1

    def test_no_overlapping_files(self, game_disc):
        """No two files occupy the same sectors."""
        occupied = []
        for entry in game_disc.files:
            start = entry.start_sector
            end = start + entry.sectors_required
            occupied.append((start, end, entry.path))

        # Check for overlaps
        occupied.sort()
        for i in range(len(occupied) - 1):
            _, end_a, path_a = occupied[i]
            start_b, _, path_b = occupied[i + 1]
            assert end_a <= start_b, (
                f"Files overlap: {path_a} ends at sector {end_a}, "
                f"{path_b} starts at sector {start_b}"
            )


class TestGameDiscFileLoading:
    """Verify every file on each game disc can be loaded successfully."""

    def test_load_all_files(self, game_disc):
        """Every file listed in the catalogue can be loaded."""
        for entry in game_disc.files:
            data = game_disc.load(entry.path)
            assert len(data) == entry.length, (
                f"File {entry.path}: loaded {len(data)} bytes, "
                f"expected {entry.length}"
            )

    def test_load_preserves_data(self, game_disc):
        """Loading the same file twice returns identical data."""
        for entry in game_disc.files:
            data1 = game_disc.load(entry.path)
            data2 = game_disc.load(entry.path)
            assert data1 == data2, f"File {entry.path}: non-deterministic load"


class TestGameDiscFileInfo:
    """Verify get_file_info() works for every file on each game disc."""

    def test_file_info_for_all_files(self, game_disc):
        """get_file_info() returns consistent metadata for every file."""
        for entry in game_disc.files:
            info = game_disc.get_file_info(entry.path)
            assert info.name == entry.path
            assert info.filename == entry.filename
            assert info.directory == entry.directory
            assert info.locked == entry.locked
            assert info.load_address == entry.load_address
            assert info.exec_address == entry.exec_address
            assert info.length == entry.length
            assert info.start_sector == entry.start_sector


class TestGameDiscPythonicInterface:
    """Verify Pythonic protocols work against each game disc."""

    def test_len_matches_files(self, game_disc):
        """len(dfs) matches len(dfs.files)."""
        assert len(game_disc) == len(game_disc.files)

    def test_contains_all_listed_files(self, game_disc):
        """Every file from .files is found by the 'in' operator."""
        for entry in game_disc.files:
            assert entry.path in game_disc, f"{entry.path} not found via 'in' operator"

    def test_contains_rejects_nonexistent(self, game_disc):
        """A file that doesn't exist is not found by 'in'."""
        assert "$.ZZZZZZZ" not in game_disc

    def test_iteration_yields_all_files(self, game_disc):
        """Iterating yields the same files as .files."""
        iterated = list(game_disc)
        assert iterated == game_disc.files

    def test_repr_is_string(self, game_disc):
        """repr() returns a non-empty string."""
        r = repr(game_disc)
        assert isinstance(r, str)
        assert len(r) > 0

    def test_str_is_string(self, game_disc):
        """str() returns a non-empty string."""
        s = str(game_disc)
        assert isinstance(s, str)
        assert len(s) > 0


class TestGameDiscValidation:
    """Verify disc validation passes for each game disc."""

    def test_validate_no_errors(self, game_disc):
        """Disc validation reports no errors."""
        errors = game_disc.validate()
        assert len(errors) == 0, f"Validation errors: {errors}"

    def test_free_sectors_non_negative(self, game_disc):
        """Free sector count is non-negative."""
        assert game_disc.free_sectors >= 0

    def test_free_plus_used_equals_available(self, game_disc):
        """Free sectors plus used sectors equals total minus catalogue."""
        total = game_disc.info["total_sectors"]
        catalogue_sectors = 2
        used = sum(entry.sectors_required for entry in game_disc.files)
        available = total - catalogue_sectors
        # Free sectors may be less than (available - used) due to fragmentation gaps
        # but should never exceed it
        assert game_disc.free_sectors <= available - used
