"""Text codecs for Acorn computer character sets.

This is the bottom layer of the oaknut workspace alongside
``oaknut-exception``: a dependency-free home for the character-set codecs
shared by the file, filesystem and language packages. Splitting the
codecs out lets siblings such as ``oaknut-basic`` use the ``"acorn"``
encoding without taking a dependency on ``oaknut-file``.

Importing this package registers the ``"acorn"`` codec as a side effect,
so ``"text".encode("acorn")`` works anywhere once any oaknut package has
been imported.
"""

from __future__ import annotations

from oaknut.codecs.acorn import (
    BBC_MICRO_TO_UNICODE,
    UNICODE_TO_BBC_MICRO,
    AcornCodec,
    acorn_to_unicode,
    unicode_to_acorn,
)

__version__ = "12.14.1"

__all__ = [
    "BBC_MICRO_TO_UNICODE",
    "UNICODE_TO_BBC_MICRO",
    "AcornCodec",
    "acorn_to_unicode",
    "unicode_to_acorn",
]
