"""Phases 17 + 18 — shipped library images + host-tree import."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import LibraryImage, import_host_tree
from oaknut.afs.host_import import _sanitise_name


class TestLibraryImageEnum:
    def test_enum_has_four_values(self) -> None:
        assert len(LibraryImage.all()) == 4

    def test_values_are_img_filenames(self) -> None:
        for entry in LibraryImage:
            assert entry.value.endswith(".img")

    def test_all_available_after_build(self) -> None:
        for entry in LibraryImage:
            assert entry.is_available()

    def test_open_reads_root(self) -> None:
        with LibraryImage.UTILS.open() as afs:
            names = [p.name for p in afs.root]
            assert "Passwords" in names


class TestSanitiseName:
    def test_passes_short_clean_name(self) -> None:
        assert _sanitise_name("Hello") == "Hello"

    def test_replaces_dot_with_underscore(self) -> None:
        assert _sanitise_name("a.b") == "a_b"

    def test_replaces_space(self) -> None:
        assert _sanitise_name("a b") == "a_b"

    def test_truncates_long_name(self) -> None:
        result = _sanitise_name("ABCDEFGHIJKLMN")
        assert len(result) == 10

    def test_empty_becomes_unnamed(self) -> None:
        assert _sanitise_name("") == "UNNAMED"

    def test_all_forbidden_becomes_underscores(self) -> None:
        result = _sanitise_name(".:./")
        assert result == "____"


class TestImportHostTree:
    def test_import_simple_tree(self, tmp_path: Path) -> None:
        # Build a tiny host tree.
        (tmp_path / "A").write_bytes(b"alpha")
        (tmp_path / "B").write_bytes(b"beta")
        sub = tmp_path / "Sub"
        sub.mkdir()
        (sub / "Inner").write_bytes(b"inner")

        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        import_host_tree(afs, source=tmp_path, target_path=afs.root / "Imp")

        assert (afs.root / "Imp" / "A").read_bytes() == b"alpha"
        assert (afs.root / "Imp" / "B").read_bytes() == b"beta"
        assert (afs.root / "Imp" / "Sub" / "Inner").read_bytes() == b"inner"

    def test_import_sanitises_names(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_bytes(b"x")
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        import_host_tree(afs, source=tmp_path, target_path=afs.root / "Land")
        assert (afs.root / "Land" / "file_txt").read_bytes() == b"x"

    def test_import_non_directory_rejected(self, tmp_path: Path) -> None:
        file = tmp_path / "not-a-dir"
        file.write_bytes(b"x")
        adfs = build_synthetic_adfs_with_afs()
        afs = adfs.afs_partition
        with pytest.raises(Exception, match="not a directory"):
            import_host_tree(afs, source=file)
