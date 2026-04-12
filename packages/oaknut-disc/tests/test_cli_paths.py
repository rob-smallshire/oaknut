"""Tests for the filing-system prefix parser."""

from __future__ import annotations

from pathlib import Path

import pytest
from oaknut.disc.cli_paths import (
    FilingSystem,
    detect_filing_system,
    parse_image_path,
    parse_prefix,
    resolve_path,
    validate_prefix_for_image,
)


class TestParsePrefix:
    def test_no_prefix(self) -> None:
        fs, bare = parse_prefix("$.Games.Elite")
        assert fs is None
        assert bare == "$.Games.Elite"

    def test_dfs_prefix(self) -> None:
        fs, bare = parse_prefix("dfs:$.Hello")
        assert fs is FilingSystem.DFS
        assert bare == "$.Hello"

    def test_adfs_prefix(self) -> None:
        fs, bare = parse_prefix("adfs:$")
        assert fs is FilingSystem.ADFS
        assert bare == "$"

    def test_afs_prefix(self) -> None:
        fs, bare = parse_prefix("afs:$.Library")
        assert fs is FilingSystem.AFS
        assert bare == "$.Library"

    def test_case_insensitive(self) -> None:
        fs, bare = parse_prefix("AFS:$.Foo")
        assert fs is FilingSystem.AFS
        assert bare == "$.Foo"

    def test_mixed_case(self) -> None:
        fs, bare = parse_prefix("Adfs:$.Bar")
        assert fs is FilingSystem.ADFS
        assert bare == "$.Bar"

    def test_prefix_only(self) -> None:
        fs, bare = parse_prefix("afs:")
        assert fs is FilingSystem.AFS
        assert bare == ""

    def test_empty_string(self) -> None:
        fs, bare = parse_prefix("")
        assert fs is None
        assert bare == ""

    def test_colon_in_path_not_prefix(self) -> None:
        # Only recognised prefixes match; an unknown prefix passes through.
        fs, bare = parse_prefix("net:$.Server")
        assert fs is None
        assert bare == "net:$.Server"


class TestDetectFilingSystem:
    def test_ssd_is_dfs(self, tmp_path: Path) -> None:
        p = tmp_path / "test.ssd"
        p.write_bytes(b"\x00" * 100)
        assert detect_filing_system(p) is FilingSystem.DFS

    def test_dsd_is_dfs(self, tmp_path: Path) -> None:
        p = tmp_path / "test.dsd"
        p.write_bytes(b"\x00" * 100)
        assert detect_filing_system(p) is FilingSystem.DFS

    def test_adl_is_adfs(self, tmp_path: Path) -> None:
        p = tmp_path / "test.adl"
        p.write_bytes(b"\x00" * 100)
        assert detect_filing_system(p) is FilingSystem.ADFS

    def test_adf_is_adfs(self, tmp_path: Path) -> None:
        p = tmp_path / "test.adf"
        p.write_bytes(b"\x00" * 100)
        assert detect_filing_system(p) is FilingSystem.ADFS

    def test_dat_is_adfs(self, tmp_path: Path) -> None:
        p = tmp_path / "test.dat"
        p.write_bytes(b"\x00" * 100)
        assert detect_filing_system(p) is FilingSystem.ADFS

    def test_unknown_extension_raises(self, tmp_path: Path) -> None:
        import click

        p = tmp_path / "test.xyz"
        p.write_bytes(b"\x00" * 100)
        with pytest.raises(click.ClickException, match="cannot detect filing system"):
            detect_filing_system(p)


class TestValidatePrefixForImage:
    def test_dfs_on_adfs_raises(self) -> None:
        import click

        with pytest.raises(click.ClickException, match="cannot access as DFS"):
            validate_prefix_for_image(FilingSystem.DFS, FilingSystem.ADFS)

    def test_adfs_on_dfs_raises(self) -> None:
        import click

        with pytest.raises(click.ClickException, match="cannot access as ADFS"):
            validate_prefix_for_image(FilingSystem.ADFS, FilingSystem.DFS)

    def test_afs_on_dfs_raises(self) -> None:
        import click

        with pytest.raises(click.ClickException, match="AFS partitions exist only on ADFS"):
            validate_prefix_for_image(FilingSystem.AFS, FilingSystem.DFS)

    def test_adfs_on_adfs_ok(self) -> None:
        # Should not raise.
        validate_prefix_for_image(FilingSystem.ADFS, FilingSystem.ADFS)

    def test_afs_on_adfs_ok(self) -> None:
        # Should not raise (AFS partition check happens later).
        validate_prefix_for_image(FilingSystem.AFS, FilingSystem.ADFS)

    def test_dfs_on_dfs_ok(self) -> None:
        validate_prefix_for_image(FilingSystem.DFS, FilingSystem.DFS)


class TestResolvePath:
    def test_none_path_uses_detection(self, tmp_path: Path) -> None:
        p = tmp_path / "test.ssd"
        p.write_bytes(b"\x00" * 100)
        fs, bare = resolve_path(p, None)
        assert fs is FilingSystem.DFS
        assert bare == ""

    def test_bare_path_uses_detection(self, tmp_path: Path) -> None:
        p = tmp_path / "test.adl"
        p.write_bytes(b"\x00" * 100)
        fs, bare = resolve_path(p, "$.Games")
        assert fs is FilingSystem.ADFS
        assert bare == "$.Games"

    def test_explicit_prefix(self, tmp_path: Path) -> None:
        p = tmp_path / "test.adl"
        p.write_bytes(b"\x00" * 100)
        fs, bare = resolve_path(p, "afs:$.Library")
        assert fs is FilingSystem.AFS
        assert bare == "$.Library"

    def test_mismatch_raises(self, tmp_path: Path) -> None:
        import click

        p = tmp_path / "test.ssd"
        p.write_bytes(b"\x00" * 100)
        with pytest.raises(click.ClickException, match="cannot access as ADFS"):
            resolve_path(p, "adfs:$")


class TestParseImagePath:
    """Tests for the image:path colon syntax parser."""

    def test_simple_colon_split(self, tmp_path: Path) -> None:
        img = tmp_path / "disc.ssd"
        img.write_bytes(b"\x00" * 100)
        result = parse_image_path(f"{img}:$.Hello")
        assert result is not None
        assert result[0] == img
        assert result[1] == "$.Hello"

    def test_with_fs_prefix(self, tmp_path: Path) -> None:
        img = tmp_path / "disc.adl"
        img.write_bytes(b"\x00" * 100)
        result = parse_image_path(f"{img}:afs:$.Library")
        assert result is not None
        assert result[0] == img
        assert result[1] == "afs:$.Library"

    def test_no_colon_returns_none(self) -> None:
        assert parse_image_path("$.Hello") is None

    def test_nonexistent_file_returns_none(self) -> None:
        assert parse_image_path("/no/such/file.ssd:$.Hello") is None

    def test_bare_image_no_path(self, tmp_path: Path) -> None:
        img = tmp_path / "disc.ssd"
        img.write_bytes(b"\x00" * 100)
        result = parse_image_path(f"{img}:")
        assert result is not None
        assert result[0] == img
        assert result[1] == ""

    def test_windows_drive_letter_skipped(self, tmp_path: Path) -> None:
        # C:\path looks like a drive letter — the first colon is not a split point.
        # This should return None since C: is not a real file in tmp_path.
        assert parse_image_path(r"C:\images\disc.ssd:$.Hello") is None

    def test_windows_drive_with_real_file(self, tmp_path: Path) -> None:
        # Simulate a path that starts with what looks like a drive letter
        # but where the actual file exists after the drive prefix.
        # On Unix this is just a directory named "C" — tests the logic.
        d = tmp_path / "C"
        d.mkdir()
        img = d / "disc.ssd"
        img.write_bytes(b"\x00" * 100)
        # The path C/disc.ssd doesn't start with X:\ so it's not a drive letter.
        result = parse_image_path(f"{img}:$.Test")
        assert result is not None
        assert result[0] == img
