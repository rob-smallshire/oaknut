"""Phases 17 + 18 — shipped library images + host-tree import."""

from __future__ import annotations

from pathlib import Path

import pytest
from helpers.afs_image import build_synthetic_adfs_with_afs
from oaknut.afs import SHIPPED_LIBRARIES, import_host_tree
from oaknut.afs.host_import import _sanitise_name
from oaknut.afs.libraries import open_shipped, shipped_available


class TestShippedLibraries:
    def test_four_shipped_libraries(self) -> None:
        assert len(SHIPPED_LIBRARIES) == 4

    def test_all_available_after_build(self) -> None:
        for name in SHIPPED_LIBRARIES:
            assert shipped_available(name)

    def test_open_reads_root(self) -> None:
        with open_shipped("Library") as adfs:
            names = [p.name for p in adfs.root.iterdir()]
            assert len(names) > 0
            # Library images are pure ADFS content — no Passwords file.
            assert "Passwords" not in names

    @pytest.mark.parametrize("name", SHIPPED_LIBRARIES)
    def test_every_file_has_load_or_exec_address(self, name: str) -> None:
        """Regression guard: a build that loses the Pi Econet Bridge xattrs
        zeros every load and exec address, which renders the library useless
        as an L3FS install. Assert per-file that *something* survived — a
        legitimate ``CopyFiles`` may carry ``load = 0`` (a BASIC program
        relocatable at boot) while still having a non-zero exec address.
        """
        with open_shipped(name) as adfs:
            files_seen = 0
            for entry in adfs.root.iterdir():
                if not entry.is_file():
                    continue
                files_seen += 1
                meta = entry.stat()
                assert meta.load_address != 0 or meta.exec_address != 0, (
                    f"{name}.adl:{entry.name} has zero load and zero exec address — "
                    "the build dropped the Pi Econet Bridge metadata"
                )
            assert files_seen > 0, f"{name}.adl appears to be empty"

    @pytest.mark.parametrize("name", SHIPPED_LIBRARIES)
    def test_load_addresses_match_source_xattrs(self, name: str) -> None:
        """Sample one well-known file per image and check the load address
        equals the upstream Pi Econet Bridge ``user.econet_load`` value.
        Catches both a complete-loss regression *and* a subtle byte-order
        or scaling error that would slip past the looser "non-zero" check.
        """
        # (filename, expected load address) — values come straight from the
        # upstream tarball at https://zxnet.co.uk/beeb/econet-fs.tar.
        # FFFFDD00 is the BBC client library module load address.
        expected = {
            "Library": ("FindLib", 0xFFFFDD00),
            "Library1": ("Discs", 0xFFFFDD00),
            "ArthurLib": ("SetFree", 0xFFFFFC40),
            "Utils": ("TreeCopy", 0xFFFF1B00),
        }
        sample_name, sample_load = expected[name]
        with open_shipped(name) as adfs:
            entry = adfs.root / sample_name
            assert entry.exists(), f"sample file {sample_name} missing from {name}.adl"
            assert entry.stat().load_address == sample_load


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
