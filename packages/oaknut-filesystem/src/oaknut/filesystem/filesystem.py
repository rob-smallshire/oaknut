"""The Filesystem extension contract.

A :class:`Filesystem` is the unit of extension — Acorn DFS, Watford
DDFS, Opus DDOS, ADFS, AFS, … as peers, registered on the
``oaknut.filesystem`` entry-point axis. It unifies *detection* and
*operations*: there is no separate prober. Each filesystem knows how to
recognise itself (:meth:`probe`), open a region (:meth:`open`), and which
physical geometries it supports (:meth:`geometry_grammar`).
"""

from __future__ import annotations

from abc import abstractmethod

from oaknut.extension import Extension, namespace_for
from oaknut.filesystem.capabilities import Mount
from oaknut.filesystem.geometry import Geometry, GeometryGrammar
from oaknut.filesystem.identification import Identification
from oaknut.filesystem.reader import ImageReader

#: The extension *kind* (axis) filesystems belong to.
FILESYSTEM_KIND = "filesystem"

#: The entry-point namespace filesystems register under: ``"oaknut.filesystem"``.
FILESYSTEM_NAMESPACE = namespace_for(FILESYSTEM_KIND)


class Filesystem(Extension):
    """Base class for a pluggable filesystem.

    Registered under ``oaknut.filesystem`` in a package's
    ``pyproject.toml``::

        [project.entry-points."oaknut.filesystem"]
        acorn_dfs = "oaknut.dfs.filesystem:AcornDFS"

    The entry-point key (``acorn-dfs``) is the filesystem's user-facing
    name: enumerated by ``disc list-filesystems``, explained by
    ``disc describe-filesystem``, and forced by ``--filesystem``.
    """

    #: Extensions conventionally used for this filesystem (lower-case,
    #: with leading dot). Consulted by the coordinator only to break ties
    #: between equally-confident candidates — never to identify.
    extensions: frozenset[str] = frozenset()
    #: Ordering hint among same-confidence, same-extension candidates;
    #: higher wins (e.g. Watford outranks Acorn DFS, which excludes it).
    priority: int = 0

    @classmethod
    def _kind(cls) -> str:
        return FILESYSTEM_KIND

    @abstractmethod
    def probe(self, reader: ImageReader) -> Identification | None:
        """Inspect the region in *reader*; identify it, or return ``None``.

        On a match, return an :class:`Identification` carrying the
        confidence, evidence, the **proposed geometry** (only this
        filesystem can read its own capacity hints), any geometry
        ambiguities the bytes cannot settle, and — for a host filesystem
        — the ``reserved_regions`` for the coordinator to recurse into.
        Must not raise on data that simply isn't this filesystem.
        """
        raise NotImplementedError

    @abstractmethod
    def open(self, reader: ImageReader, geometry: Geometry) -> Mount:
        """Open the region in *reader* at *geometry*, returning a mount.

        The returned object implements :class:`Mount` plus whichever
        capability protocols this filesystem supports.
        """
        raise NotImplementedError

    @abstractmethod
    def geometry_grammar(self) -> GeometryGrammar:
        """The geometries this filesystem supports — presets and kinds.

        Used to resolve ``--geometry`` and to enumerate choices for
        ``disc create`` and ``describe-filesystem``.
        """
        raise NotImplementedError
