"""The Filesystem extension contract.

A :class:`Filesystem` is the unit of extension — Acorn DFS, Watford
DFS, Opus DDOS, ADFS, AFS, … as peers, registered on the
``oaknut.filesystem`` entry-point axis. It unifies *detection* and
*operations*: there is no separate prober. Each filesystem knows how to
recognise itself (:meth:`probe`), open a region (:meth:`open`), and which
physical geometries it supports (:meth:`geometry_grammar`).
"""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

from oaknut.extension import Extension, namespace_for
from oaknut.filesystem.capabilities import Mount
from oaknut.filesystem.exceptions import FilesystemError
from oaknut.filesystem.geometry import Geometry, GeometryGrammar
from oaknut.filesystem.identification import Identification, Volume
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
    #: Extensions this filesystem is the *default creator* for — ``disc
    #: create`` infers the filesystem from the target's extension via
    #: this. A subset of (or disjoint from) :attr:`extensions`: a niche
    #: variant (Watford) or a non-standalone filesystem (AFS, made inside
    #: an ADFS disc) leaves it empty and is reached only via
    #: ``--filesystem``.
    creates: frozenset[str] = frozenset()

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
    def open(self, reader: ImageReader, geometry: Geometry, *, surface: int = 0) -> Mount:
        """Open the region in *reader* at *geometry*, returning a mount.

        The returned object implements :class:`Mount` plus whichever
        capability protocols this filesystem supports. *surface* selects
        which volume of a multi-volume image to open (a DFS side); the
        default 0 is the whole image / first volume, which is all most
        filesystems have.
        """
        raise NotImplementedError

    def split_volume(
        self, inner_path: str, geometry: Geometry, ambiguities: tuple[Geometry, ...] = ()
    ) -> tuple[int, Geometry, str]:
        """Split a leading volume token from *inner_path*.

        Returns ``(surface_index, geometry, residual_path)``. The
        returned geometry may differ from the one passed in, because the
        volume token can *imply* a geometry — a non-zero DFS drive on a
        length-ambiguous image implies the double-sided reading drawn
        from *ambiguities*. The default has no notion of a sub-volume:
        surface 0, the geometry unchanged, and the whole path. DFS
        overrides this to parse the Acorn ``:drive.`` prefix.
        """
        return 0, geometry, inner_path

    def volumes(self, geometry: Geometry) -> tuple[Volume, ...]:
        """The independently-addressable volumes at *geometry*.

        The default is a single, undesignated volume — most filesystems
        span the whole image. A double-sided DFS reports one per side,
        designated ``:0`` / ``:2``. Round-trips with :meth:`split_volume`:
        every designation here parses back to the same surface.
        """
        return (Volume(designation="", surface=0),)

    def designation_for(self, surface: int, geometry: Geometry) -> str:
        """The user-facing designation of *surface*, for diagnostics.

        Looks the surface up among :meth:`volumes`, so messages quote the
        filesystem's own vocabulary (``:2``, not the cardinal index). A
        surface with no enumerated volume falls back to ``:N`` so a
        diagnostic about an *absent* second side still reads naturally.
        """
        for volume in self.volumes(geometry):
            if volume.surface == surface:
                return volume.designation
        return f":{surface}"

    @abstractmethod
    def geometry_grammar(self) -> GeometryGrammar:
        """The geometries this filesystem supports — presets and kinds.

        Used to resolve ``--geometry`` and to enumerate choices for
        ``disc create`` and ``describe-filesystem``.
        """
        raise NotImplementedError

    def default_geometry(self, suffix: str) -> Geometry | None:
        """The geometry to create a *suffix* image with, or ``None``.

        ``None`` means there is no sensible default for this extension —
        it is ambiguous (ADFS ``.adf`` could be S or M) or open-ended (a
        hard disc) — so ``disc create`` requires an explicit
        ``--geometry``. The default implementation has none.
        """
        return None

    def create(self, filepath: Path, geometry: Geometry, *, title: str) -> None:
        """Create a new empty image of this filesystem at *filepath*.

        Filesystems that are not created standalone (AFS lives inside an
        ADFS disc; archives) do not override this and decline.
        """
        raise FilesystemError(f"{self.name} images cannot be created with `disc create`")
