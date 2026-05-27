"""ZIP archives as an oaknut.filesystem extension.

A ZIP is a *container* — it may hold Acorn files with RISC OS metadata —
rather than an Acorn disc, so it has no geometry and is read-only. But it
*is* a browsable hierarchy of files carrying load/exec/access/filetype,
so the mount presents one: ``disc ls`` / ``tree`` / ``cat`` / ``get``
work, and the Acorn metadata recovered from SparkFS extras, ``.inf``
sidecars, and filename encoding surfaces through the
:class:`~oaknut.filesystem.AcornMetadata` capability.

The mount is a thin adapter over this package's archive API: member
enumeration and metadata resolution are :func:`oaknut.zip.api.resolved_entries`;
the mount only adds the directory tree that a ZIP's flat namespace
implies.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable

from oaknut.file import AcornMeta
from oaknut.filesystem import (
    Confidence,
    Entry,
    Filesystem,
    Geometry,
    GeometryGrammar,
    Identification,
    ImageReader,
)

from .api import resolved_entries

_SIGNATURES = {
    b"PK\x03\x04": "local file header",
    b"PK\x05\x06": "empty archive",
    b"PK\x07\x08": "spanned archive",
}


class _ZipMount:
    """A read-only :class:`~oaknut.filesystem.Mount` over a ZIP archive.

    Members are addressed by their cleaned path (``dir/file``) — a
    filename-encoded suffix such as ``,ff9`` stripped — under a nameless
    root (``""``). The flat ZIP namespace is presented as a directory
    tree, synthesising directories the archive does not store explicitly.
    """

    def __init__(self, archive: zipfile.ZipFile):
        self._archive = archive
        self._entry: dict[str, Entry] = {"": Entry(name="", is_dir=True, path="")}
        self._children: dict[str, list[Entry]] = {"": []}
        self._member: dict[str, str] = {}
        self._meta: dict[str, AcornMeta] = {}
        self._build()

    def _build(self) -> None:
        for resolved in resolved_entries(self._archive):
            path = resolved.name.rstrip("/")
            if not path:
                continue
            parent = path.rpartition("/")[0]
            self._ensure_dir(parent)
            if resolved.is_dir:
                self._ensure_dir(path)
                if resolved.meta is not None:
                    self._meta[path] = resolved.meta
                continue
            name = path.rpartition("/")[2]
            entry = Entry(name=name, is_dir=False, length=resolved.file_size, path=path)
            self._entry[path] = entry
            self._member[path] = resolved.member
            self._children[parent].append(entry)
            if resolved.meta is not None and resolved.meta.has_metadata:
                self._meta[path] = resolved.meta

    def _ensure_dir(self, path: str) -> None:
        """Register *path* (and any missing ancestors) as a directory."""
        if path in self._entry:
            return
        parent = path.rpartition("/")[0]
        self._ensure_dir(parent)
        entry = Entry(name=path.rpartition("/")[2], is_dir=True, path=path)
        self._entry[path] = entry
        self._children[path] = []
        self._children[parent].append(entry)

    def path_root(self) -> str:
        return ""

    def stat(self, path: str) -> Entry:
        try:
            return self._entry[path]
        except KeyError:
            raise FileNotFoundError(path) from None

    def join(self, parent: str, name: str) -> str:
        # ZIP member names are POSIX paths under a nameless root.
        return f"{parent}/{name}" if parent else name

    def iter_entries(self, path: str) -> Iterable[Entry]:
        return tuple(self._children.get(path, ()))

    def exists(self, path: str) -> bool:
        return path in self._entry

    def read_bytes(self, path: str) -> bytes:
        return self._archive.read(self._member[path])

    def acorn_meta(self, path: str) -> AcornMeta:
        return self._meta.get(path, AcornMeta())

    def set_acorn_meta(self, path: str, meta: AcornMeta) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")

    def write_bytes(self, path: str, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")

    def remove(self, path: str, *, force: bool = False) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")

    def rename(self, old_path: str, new_path: str) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")


class Zip(Filesystem):
    """ZIP — archives that may carry Acorn files (SparkFS extras, RISC OS types).

    Detected by the unambiguous ``PK`` signature. The mount browses the
    archive read-only and surfaces the Acorn metadata this package's
    archive API recovers.
    """

    extensions = frozenset({".zip"})

    def probe(self, reader: ImageReader) -> Identification | None:
        kind = _SIGNATURES.get(reader.read(0, 4))
        if kind is None:
            return None
        return Identification(
            filesystem=self.name,
            confidence=Confidence.CERTAIN,
            evidence=(f"ZIP signature ({kind}) at offset 0",),
        )

    def open(self, reader: ImageReader, geometry: Geometry | None = None) -> _ZipMount:
        data = reader.read(0, reader.size)
        return _ZipMount(zipfile.ZipFile(io.BytesIO(data)))

    def geometry_grammar(self) -> GeometryGrammar:
        # A ZIP has no disc geometry.
        return GeometryGrammar()
