"""Tests for ADFS.create_file extension-based format defaults.

When ``adfs_format`` is omitted, the format is inferred from the
filename extension where the extension makes the choice unambiguous:

- ``.ads`` → :data:`ADFS_S` (40T × 16spt × 1 side, 160KB)
- ``.adm`` → :data:`ADFS_M` (80T × 16spt × 1 side, 320KB)
- ``.adl`` → :data:`ADFS_L` (80T × 16spt × 2 sides, 640KB)

``.adf`` is ambiguous (used historically for both S and M sizes) and
still requires an explicit format. Hard-disc images (``.dat`` /
``.dsc``) use capacity-based geometry instead and are not affected.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.adfs import ADFS, ADFS_L, ADFS_M, ADFS_S
from oaknut.adfs.exceptions import ADFSFormatError


class TestAdfsCreateFileAutoDetect:
    def test_ads_extension_defaults_to_adfs_s(self, tmp_path: Path) -> None:
        filepath = tmp_path / "fresh.ads"
        with ADFS.create_file(filepath, title="X"):
            pass
        assert filepath.stat().st_size == ADFS_S.total_bytes

    def test_adm_extension_defaults_to_adfs_m(self, tmp_path: Path) -> None:
        filepath = tmp_path / "fresh.adm"
        with ADFS.create_file(filepath, title="X"):
            pass
        assert filepath.stat().st_size == ADFS_M.total_bytes

    def test_adl_extension_defaults_to_adfs_l(self, tmp_path: Path) -> None:
        filepath = tmp_path / "fresh.adl"
        with ADFS.create_file(filepath, title="X"):
            pass
        assert filepath.stat().st_size == ADFS_L.total_bytes

    def test_explicit_format_overrides_extension(self, tmp_path: Path) -> None:
        """An explicit ``adfs_format`` always wins, even when the
        extension would imply something else.
        """
        filepath = tmp_path / "named.adl"
        with ADFS.create_file(filepath, ADFS_S):
            pass
        assert filepath.stat().st_size == ADFS_S.total_bytes

    def test_unknown_extension_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ADFSFormatError):
            with ADFS.create_file(tmp_path / "fresh.unknown"):
                pass

    def test_adf_remains_ambiguous(self, tmp_path: Path) -> None:
        """``.adf`` has been used for both S and M sizes; the API
        refuses to guess. Same error as any other unrecognised
        extension.
        """
        with pytest.raises(ADFSFormatError):
            with ADFS.create_file(tmp_path / "fresh.adf"):
                pass
