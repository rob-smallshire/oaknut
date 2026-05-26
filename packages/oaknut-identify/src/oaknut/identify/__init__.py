"""Content-based identification of Acorn disc-image formats.

Disc-image extensions are conventions that are often missing or wrong.
This package answers "what is actually in this image?" by reading the
bytes: a cascade of pluggable :class:`Prober` extensions (discovered
through the ``oaknut.prober`` entry-point namespace) inspect the image
and emit ranked :class:`Identification` candidates.

The public entry point is :func:`identify`::

    from oaknut.identify import identify

    for candidate in identify("mystery.img"):
        print(candidate.family, candidate.confidence.name, candidate.evidence)
"""

from oaknut.identify.coordinator import (
    create_prober,
    describe_prober,
    identify,
    prober_names,
)
from oaknut.identify.prober import (
    PROBER_KIND,
    PROBER_NAMESPACE,
    Confidence,
    Identification,
    Prober,
)
from oaknut.identify.reader import ImageReader, ImageSource, reader_for

__version__ = "11.2.0"

__all__ = [
    "Confidence",
    "Identification",
    "ImageReader",
    "ImageSource",
    "PROBER_KIND",
    "PROBER_NAMESPACE",
    "Prober",
    "create_prober",
    "describe_prober",
    "identify",
    "prober_names",
    "reader_for",
]
