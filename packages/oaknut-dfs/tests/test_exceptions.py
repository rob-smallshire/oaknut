"""Tests for custom exception hierarchy."""

import pytest
from oaknut_dfs.exceptions import (
    FSError,
    DFSError,
    CatalogError,
    CatalogReadError,
    CatalogFullError,
    FileExistsError,
    DiskFullError,
    FileLocked,
    InvalidFormatError,
    ADFSError,
    ADFSDirectoryError,
    ADFSMapError,
    ADFSPathError,
    ADFSDiscFullError,
    ADFSDirectoryFullError,
    ADFSFileLockedError,
)


class TestExceptionHierarchy:
    """Test exception inheritance and hierarchy."""

    def test_fs_error_derives_from_exception(self):
        """FSError should inherit from base Exception."""
        assert issubclass(FSError, Exception)

    def test_dfs_error_derives_from_fs_error(self):
        """DFSError should inherit from FSError."""
        assert issubclass(DFSError, FSError)

    def test_adfs_error_derives_from_fs_error(self):
        """ADFSError should inherit from FSError."""
        assert issubclass(ADFSError, FSError)

    def test_all_dfs_exceptions_derive_from_dfs_error(self):
        """All DFS exceptions should inherit from DFSError."""
        exceptions = [
            CatalogError,
            CatalogReadError,
            CatalogFullError,
            FileExistsError,
            DiskFullError,
            FileLocked,
            InvalidFormatError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, DFSError)

    def test_all_dfs_exceptions_derive_from_fs_error(self):
        """All DFS exceptions should also be catchable as FSError."""
        exceptions = [
            CatalogError,
            CatalogReadError,
            CatalogFullError,
            FileExistsError,
            DiskFullError,
            FileLocked,
            InvalidFormatError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, FSError)

    def test_catalog_exceptions_hierarchy(self):
        """Catalog-specific exceptions should inherit from CatalogError."""
        catalog_exceptions = [
            CatalogReadError,
            CatalogFullError,
            FileExistsError,
        ]

        for exc_class in catalog_exceptions:
            assert issubclass(exc_class, CatalogError)
            assert issubclass(exc_class, DFSError)

    def test_all_adfs_exceptions_derive_from_adfs_error(self):
        """All ADFS exceptions should inherit from ADFSError."""
        exceptions = [
            ADFSDirectoryError,
            ADFSMapError,
            ADFSPathError,
            ADFSDiscFullError,
            ADFSDirectoryFullError,
            ADFSFileLockedError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, ADFSError)

    def test_all_adfs_exceptions_derive_from_fs_error(self):
        """All ADFS exceptions should also be catchable as FSError."""
        exceptions = [
            ADFSDirectoryError,
            ADFSMapError,
            ADFSPathError,
            ADFSDiscFullError,
            ADFSDirectoryFullError,
            ADFSFileLockedError,
        ]

        for exc_class in exceptions:
            assert issubclass(exc_class, FSError)

    def test_adfs_disc_full_derives_from_adfs_map_error(self):
        """ADFSDiscFullError is an ADFSMapError."""
        assert issubclass(ADFSDiscFullError, ADFSMapError)

    def test_adfs_directory_full_derives_from_adfs_directory_error(self):
        """ADFSDirectoryFullError is an ADFSDirectoryError."""
        assert issubclass(ADFSDirectoryFullError, ADFSDirectoryError)


class TestExceptionCatching:
    """Test that exceptions can be caught at different hierarchy levels."""

    def test_catch_specific_catalog_read_error(self):
        """CatalogReadError can be caught specifically."""
        with pytest.raises(CatalogReadError):
            raise CatalogReadError("Corrupted catalog")

    def test_catch_catalog_read_error_as_catalog_error(self):
        """CatalogReadError can be caught as CatalogError."""
        with pytest.raises(CatalogError):
            raise CatalogReadError("Corrupted catalog")

    def test_catch_catalog_read_error_as_dfs_error(self):
        """CatalogReadError can be caught as DFSError."""
        with pytest.raises(DFSError):
            raise CatalogReadError("Corrupted catalog")

    def test_catch_catalog_read_error_as_fs_error(self):
        """CatalogReadError can be caught as FSError."""
        with pytest.raises(FSError):
            raise CatalogReadError("Corrupted catalog")

    def test_catch_any_dfs_error(self):
        """Any DFS exception can be caught with DFSError."""
        exceptions = [
            CatalogReadError("read error"),
            CatalogFullError("full"),
            DiskFullError("no space"),
            FileLocked("locked"),
            InvalidFormatError("bad format"),
        ]

        for exc in exceptions:
            with pytest.raises(DFSError):
                raise exc

    def test_catch_any_adfs_error(self):
        """Any ADFS exception can be caught with ADFSError."""
        exceptions = [
            ADFSDirectoryError("bad dir"),
            ADFSMapError("bad map"),
            ADFSPathError("bad path"),
            ADFSDiscFullError("no space"),
            ADFSDirectoryFullError("dir full"),
            ADFSFileLockedError("locked"),
        ]

        for exc in exceptions:
            with pytest.raises(ADFSError):
                raise exc

    def test_catch_any_error_with_fs_error(self):
        """Both DFS and ADFS exceptions can be caught with FSError."""
        exceptions = [
            DFSError("dfs"),
            CatalogReadError("read error"),
            DiskFullError("no space"),
            ADFSError("adfs"),
            ADFSDirectoryError("bad dir"),
            ADFSDiscFullError("no space"),
        ]

        for exc in exceptions:
            with pytest.raises(FSError):
                raise exc


class TestExceptionMessages:
    """Test that exceptions preserve error messages."""

    def test_fs_error_with_message(self):
        """FSError preserves error message."""
        msg = "Test error message"
        with pytest.raises(FSError, match=msg):
            raise FSError(msg)

    def test_dfs_error_with_message(self):
        """DFSError preserves error message."""
        msg = "Test error message"
        with pytest.raises(DFSError, match=msg):
            raise DFSError(msg)

    def test_catalog_read_error_with_message(self):
        """CatalogReadError preserves error message."""
        msg = "Failed to decode catalog: invalid byte sequence"
        with pytest.raises(CatalogReadError, match=msg):
            raise CatalogReadError(msg)

    def test_disk_full_error_with_message(self):
        """DiskFullError preserves error message."""
        msg = "Cannot save file: needs 10 sectors, only 5 free"
        with pytest.raises(DiskFullError, match=msg):
            raise DiskFullError(msg)

    def test_adfs_disc_full_error_with_message(self):
        """ADFSDiscFullError preserves error message."""
        msg = "No free space region large enough for 100 sectors"
        with pytest.raises(ADFSDiscFullError, match=msg):
            raise ADFSDiscFullError(msg)

    def test_adfs_directory_full_error_with_message(self):
        """ADFSDirectoryFullError preserves error message."""
        msg = "Directory full: maximum 47 entries"
        with pytest.raises(ADFSDirectoryFullError, match=msg):
            raise ADFSDirectoryFullError(msg)


class TestExceptionInstances:
    """Test exception instance properties."""

    def test_dfs_exception_is_instance_of_hierarchy(self):
        """DFS exception instance should be instance of all parent classes."""
        exc = CatalogReadError("test")

        assert isinstance(exc, CatalogReadError)
        assert isinstance(exc, CatalogError)
        assert isinstance(exc, DFSError)
        assert isinstance(exc, FSError)
        assert isinstance(exc, Exception)

    def test_adfs_exception_is_instance_of_hierarchy(self):
        """ADFS exception instance should be instance of all parent classes."""
        exc = ADFSDiscFullError("test")

        assert isinstance(exc, ADFSDiscFullError)
        assert isinstance(exc, ADFSMapError)
        assert isinstance(exc, ADFSError)
        assert isinstance(exc, FSError)
        assert isinstance(exc, Exception)

    def test_exception_str_representation(self):
        """Exception string representation should show the message."""
        msg = "Catalog corrupted at sector 0"
        exc = CatalogReadError(msg)

        assert str(exc) == msg
