"""Tests for ``ADFSPath.touch()`` — pathlib-shaped empty-file creation."""

import pytest
from oaknut.adfs import ADFS, ADFS_S
from oaknut.adfs.exceptions import ADFSEntryExistsError, ADFSPathError
from oaknut.file import Access


class TestTouch:
    """``touch()`` creates an empty file at the path.

    Mirrors :meth:`pathlib.Path.touch`: ``exist_ok=True`` (the default)
    makes the call idempotent for an existing file; ``exist_ok=False``
    raises if anything is already at the path.
    """

    def test_touch_creates_empty_file(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").touch()
        assert (adfs.root / "Hello").exists()
        assert (adfs.root / "Hello").read_bytes() == b""

    def test_touch_applies_access_on_create(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Locked").touch(access=Access.LWR)
        st = (adfs.root / "Locked").stat()
        assert st.access & Access.L

    def test_touch_default_exist_ok_is_true(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").write_bytes(b"keep")
        (adfs.root / "Hello").touch()  # no exception
        assert (adfs.root / "Hello").read_bytes() == b"keep"

    def test_touch_exist_ok_false_raises_when_file_exists(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Hello").write_bytes(b"x")
        with pytest.raises(ADFSEntryExistsError):
            (adfs.root / "Hello").touch(exist_ok=False)

    def test_touch_exist_ok_false_raises_when_directory_exists(self):
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        with pytest.raises(ADFSPathError):
            (adfs.root / "Dir").touch(exist_ok=False)

    def test_touch_raises_when_path_is_existing_directory(self):
        """Even with exist_ok=True, touching a directory is not okay."""
        adfs = ADFS.create(ADFS_S)
        (adfs.root / "Dir").mkdir()
        with pytest.raises(ADFSPathError):
            (adfs.root / "Dir").touch()

    def test_touch_root_raises(self):
        adfs = ADFS.create(ADFS_S)
        with pytest.raises(ADFSPathError):
            adfs.root.touch()
