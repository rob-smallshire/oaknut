"""Exceptions raised by oaknut.hfe.

Hierarchy::

    DataError (oaknut.exception)
    └── HFEError
        └── HFEFormatError   the file is not a well-formed HFE image
"""

from __future__ import annotations

from oaknut.exception import DataError

__all__ = ["HFEError", "HFEFormatError"]


class HFEError(DataError):
    """Base exception for HFE errors."""


class HFEFormatError(HFEError):
    """The file is not a well-formed HFE v1 or v3 image."""
