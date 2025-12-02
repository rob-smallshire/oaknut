"""Tests for custom exception hierarchy."""

import pytest
from oaknut_dfs.exceptions import (
    DFSError,
    CatalogError,
    CatalogReadError,
    CatalogFullError,
    FileExistsError,
    DiskFullError,
    FileLocked,
    InvalidFormatError,
)


class TestExceptionHierarchy:
    """Test exception inheritance and hierarchy."""

    def test_all_exceptions_derive_from_dfs_error(self):
        """All custom exceptions should inherit from DFSError."""
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

    def test_dfs_error_derives_from_exception(self):
        """DFSError should inherit from base Exception."""
        assert issubclass(DFSError, Exception)

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


class TestExceptionMessages:
    """Test that exceptions preserve error messages."""

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


class TestExceptionInstances:
    """Test exception instance properties."""

    def test_exception_is_instance_of_hierarchy(self):
        """Exception instance should be instance of all parent classes."""
        exc = CatalogReadError("test")

        assert isinstance(exc, CatalogReadError)
        assert isinstance(exc, CatalogError)
        assert isinstance(exc, DFSError)
        assert isinstance(exc, Exception)

    def test_exception_str_representation(self):
        """Exception string representation should show the message."""
        msg = "Catalog corrupted at sector 0"
        exc = CatalogReadError(msg)

        assert str(exc) == msg
