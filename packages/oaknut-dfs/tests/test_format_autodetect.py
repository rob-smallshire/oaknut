"""Auto-detect a DFS DiskFormat from filename + size (#28).

DFS.from_file / DFS.create_file accept a None disk_format and pick
the right format from the extension and (for from_file) size, so
``DFS.from_file("foo.ssd")`` works without further arguments.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.dfs import (
    ACORN_DFS_40T_SINGLE_SIDED,
    ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_80T_SINGLE_SIDED,
    DFS,
    detect_dfs_format,
)


class TestDetectDfsFormat:
    def test_ssd_200kib_is_80t_single(self, tmp_path: Path) -> None:
        filepath = tmp_path / "x.ssd"
        filepath.write_bytes(b"\x00" * 200_000)  # close to 200 KiB
        assert detect_dfs_format(filepath) is ACORN_DFS_80T_SINGLE_SIDED

    def test_ssd_100kib_is_40t_single(self, tmp_path: Path) -> None:
        filepath = tmp_path / "x.ssd"
        filepath.write_bytes(b"\x00" * 100_000)
        assert detect_dfs_format(filepath) is ACORN_DFS_40T_SINGLE_SIDED

    def test_dsd_400kib_is_80t_double(self, tmp_path: Path) -> None:
        filepath = tmp_path / "x.dsd"
        filepath.write_bytes(b"\x00" * 400_000)
        assert detect_dfs_format(filepath) is ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

    def test_unknown_extension_raises(self, tmp_path: Path) -> None:
        filepath = tmp_path / "x.unknown"
        filepath.write_bytes(b"\x00" * 100_000)
        with pytest.raises(ValueError, match="pass disk_format= explicitly"):
            detect_dfs_format(filepath)

    def test_unexpected_size_raises(self, tmp_path: Path) -> None:
        filepath = tmp_path / "x.ssd"
        filepath.write_bytes(b"\x00" * 500_000)  # too big for either SSD variant
        with pytest.raises(ValueError, match="pass disk_format= explicitly"):
            detect_dfs_format(filepath)


class TestDfsFromFileAutoDetect:
    def test_from_file_works_without_disk_format(self, tmp_path: Path) -> None:
        filepath = tmp_path / "test.ssd"
        with DFS.create_file(filepath, title="Auto") as dfs:
            (dfs.root / "$.Hello").write_bytes(b"world", load_address=0x1900)
        # Reopen without disk_format — auto-detection should pick up
        # ACORN_DFS_80T_SINGLE_SIDED.
        with DFS.from_file(filepath) as dfs:
            assert dfs.title == "Auto"
            assert (dfs.root / "$.Hello").read_bytes() == b"world"


class TestDfsCreateFileAutoDetect:
    def test_ssd_extension_defaults_to_80t_single(self, tmp_path: Path) -> None:
        filepath = tmp_path / "fresh.ssd"
        with DFS.create_file(filepath, title="X"):
            pass
        # File must have the canonical 80-track single-sided size.
        assert filepath.stat().st_size == ACORN_DFS_80T_SINGLE_SIDED.image_size

    def test_dsd_extension_defaults_to_80t_double_interleaved(
        self, tmp_path: Path
    ) -> None:
        filepath = tmp_path / "fresh.dsd"
        with DFS.create_file(filepath):
            pass
        assert (
            filepath.stat().st_size
            == ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED.image_size
        )

    def test_unknown_extension_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cannot pick a default"):
            with DFS.create_file(tmp_path / "fresh.unknown"):
                pass
