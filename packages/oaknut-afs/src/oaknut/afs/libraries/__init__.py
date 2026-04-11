"""Shipped AFS library disc images.

Phase 17 of the oaknut-afs build provides the API surface for
bundled library disc images (Utils, Model B, Master, Archimedes)
that ``initialise(...)`` (phase 19) can merge into a freshly-
partitioned AFS region. The actual binary assets are produced by
``scripts/build_library_images.py`` from
``/Users/rjs/Code/beebium/discs/l3fs/libraries/econet-fs.tar`` —
see the script for the provenance.

The four images are:

- ``UTILS`` — shared utilities visible to every client.
- ``MODEL_B`` — the ``Library`` tree BBC B / B+ (ANFS) clients
  load from.
- ``MASTER`` — the ``Library1`` tree Master 128 / Compact clients
  load from.
- ``ARCHIMEDES`` — the ``ArthurLib`` tree Archimedes clients
  load from.

At runtime :meth:`LibraryImage.open` returns a read-only
:class:`~oaknut.afs.afs.AFS` handle on the image, backed by
``importlib.resources``. Callers who want to merge a library into
a target disc use :meth:`LibraryImage.merge_into`.
"""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from importlib import resources
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from oaknut.afs.afs import AFS
    from oaknut.afs.path import AFSPath


class LibraryImage(Enum):
    """Enum of shipped AFS library disc images.

    Each value is the filename of the binary asset inside
    ``oaknut.afs.libraries`` (an ``importlib.resources`` package).
    """

    UTILS = "library_utils.img"
    MODEL_B = "library_model_b.img"
    MASTER = "library_master.img"
    ARCHIMEDES = "library_archimedes.img"

    @classmethod
    def all(cls) -> list["LibraryImage"]:
        return list(cls)

    def is_available(self) -> bool:
        """True if the shipped binary asset is actually bundled.

        Returns False when this package was installed without the
        pre-built library images (e.g. during early development
        before the build script has run).
        """
        try:
            return resources.files(__name__).joinpath(self.value).is_file()
        except (FileNotFoundError, ModuleNotFoundError):
            return False

    @contextmanager
    def open(self) -> "Iterator[AFS]":
        """Yield a read-only :class:`AFS` handle on the shipped image.

        Raises :class:`FileNotFoundError` if the asset isn't bundled.
        """
        from oaknut.afs.afs import AFS

        if not self.is_available():
            raise FileNotFoundError(
                f"library image {self.value!r} is not bundled in this "
                f"installation of oaknut-afs; run "
                f"scripts/build_library_images.py to produce it"
            )
        with resources.as_file(
            resources.files(__name__).joinpath(self.value)
        ) as path:
            with AFS.from_file(path) as afs:
                yield afs

    def merge_into(
        self,
        target: "AFS",
        *,
        target_path: "AFSPath | None" = None,
        conflict: str = "error",
    ) -> None:
        """Merge this library's entire tree into ``target``.

        Thin wrapper around :func:`oaknut.afs.merge` for the common
        "drop a shipped library onto a fresh disc" case.
        """
        from oaknut.afs.merge import merge

        with self.open() as source:
            merge(
                target,
                source,
                target_path=target_path,
                conflict=conflict,
            )
