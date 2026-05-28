"""Tests for the mount-resolution substrate (the CLI's content-first open path)."""

import click
import pytest
from oaknut.disc.mount import ResolvedMount, resolve_mount, split_selector
from oaknut.filesystem import Mount

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"


class TestSplitSelector:
    def test_no_selector_for_acorn_path(self):
        assert split_selector("$.Games.Elite") == (None, "$.Games.Elite")
        assert split_selector("") == (None, "")
        assert split_selector("A.GAME") == (None, "A.GAME")  # DFS dir letter

    def test_selector_recognised(self):
        assert split_selector("afs:$.Library") == ("afs", "$.Library")
        assert split_selector("afs.1:$.X") == ("afs.1", "$.X")
        assert split_selector("acorn-dfs:$") == ("acorn-dfs", "$")
        assert split_selector("adfs:") == ("adfs", "")


class TestResolveMount:
    def test_dfs_image_default_partition(self, dfs_image_filepath):
        resolved = resolve_mount(str(dfs_image_filepath))
        assert isinstance(resolved, ResolvedMount)
        assert isinstance(resolved.mount, Mount)
        assert resolved.filesystem == "acorn-dfs"
        # DFS has a nameless virtual root holding the populated directory
        # letters; $ is the default one, a sibling of A, B, … The files
        # live one level down, under their letter.
        letters = {e.name for e in resolved.mount.iter_entries(resolved.mount.path_root())}
        assert "$" in letters
        files = {e.name for e in resolved.mount.iter_entries("$")}
        assert "HELLO" in files

    def test_in_partition_path_is_returned(self, dfs_image_filepath):
        resolved = resolve_mount(f"{dfs_image_filepath}:$.HELLO")
        assert resolved.path == "$.HELLO"
        assert resolved.mount.read_bytes("$.HELLO") == b"Hello world"

    def test_combined_disc_defaults_to_host(self):
        resolved = resolve_mount(str(_L3FS_DAT))
        assert resolved.filesystem == "adfs"

    def test_afs_partition_selected_by_prefix(self):
        resolved = resolve_mount(f"{_L3FS_DAT}:afs:$")
        assert resolved.filesystem == "afs"
        assert resolved.partition == "afs"
        names = {e.name for e in resolved.mount.iter_entries("$")}
        assert "HOLMES" in names

    def test_unknown_partition_errors(self, dfs_image_filepath):
        with pytest.raises(click.ClickException, match="no such partition"):
            resolve_mount(f"{dfs_image_filepath}:afs:$")

    def test_force_filesystem_overrides_detection(self, dfs_image_filepath, tmp_path):
        # DFS bytes under a meaningless name, forced as acorn-dfs.
        mystery = tmp_path / "mystery.bin"
        mystery.write_bytes(dfs_image_filepath.read_bytes())
        resolved = resolve_mount(str(mystery), force_filesystem="acorn-dfs")
        assert resolved.filesystem == "acorn-dfs"
        assert "HELLO" in {e.name for e in resolved.mount.iter_entries("$")}

    def test_unrecognised_image_errors(self, tmp_path):
        mystery = tmp_path / "mystery.bin"
        mystery.write_bytes(b"not any known disc image at all")
        with pytest.raises(click.ClickException, match="no installed filesystem recognises"):
            resolve_mount(str(mystery))


class TestWritableMount:
    def test_writable_context_manager_persists(self, dfs_image_filepath):
        # As a context manager the live mapping stays open for the write
        # and is released on exit; the change is then visible on reopen.
        with resolve_mount(f"{dfs_image_filepath}:$", writable=True) as resolved:
            resolved.mount.write_bytes("$.GREET", b"hi")
        resolved = resolve_mount(f"{dfs_image_filepath}:$")
        assert resolved.mount.read_bytes("$.GREET") == b"hi"

    def test_writable_afs_partition_on_hard_disc_persists(self, tmp_path):
        import shutil

        image_filepath = tmp_path / "l3fs.dat"
        shutil.copy(_L3FS_DAT, image_filepath)
        with resolve_mount(f"{image_filepath}:afs:$", writable=True) as resolved:
            assert resolved.filesystem == "afs"
            resolved.mount.write_bytes("$.NEWFILE", b"persisted")
        resolved = resolve_mount(f"{image_filepath}:afs:$")
        assert resolved.mount.read_bytes("$.NEWFILE") == b"persisted"
