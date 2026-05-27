"""ZIP archives as an oaknut.filesystem extension.

A ZIP is a *container* (it may hold Acorn files with RISC OS metadata),
not an Acorn disc, so this is deliberately minimal: detection by the
``PK`` signature and a read-only :class:`~oaknut.filesystem.Mount` that
lists and reads members. It advertises no Acorn-disc capabilities — the
Acorn-metadata extraction lives in this package's archive API.

Part of Phase B of the filesystem-extensibility refactor.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable

from oaknut.filesystem import (
    Confidence,
    Entry,
    Filesystem,
    Geometry,
    GeometryGrammar,
    Identification,
    ImageReader,
)

_SIGNATURES = {
    b"PK\x03\x04": "local file header",
    b"PK\x05\x06": "empty archive",
    b"PK\x07\x08": "spanned archive",
}


class _ZipMount:
    """A read-only :class:`~oaknut.filesystem.Mount` over a ZIP archive.

    Members are addressed by their archive path (``dir/file``); the root
    path is the empty string and lists every member.
    """

    def __init__(self, archive: zipfile.ZipFile):
        self._archive = archive

    def path_root(self) -> str:
        return ""

    def stat(self, path: str) -> Entry:
        info = self._archive.getinfo(path)
        return Entry(
            name=info.filename, is_dir=info.is_dir(), length=info.file_size, path=info.filename
        )

    def join(self, parent: str, name: str) -> str:
        # ZIP member names are POSIX paths under a nameless root.
        return f"{parent}/{name}" if parent else name

    def iter_entries(self, path: str) -> Iterable[Entry]:
        for info in self._archive.infolist():
            yield Entry(
                name=info.filename,
                is_dir=info.is_dir(),
                length=info.file_size,
                path=info.filename,
            )

    def exists(self, path: str) -> bool:
        return path in self._archive.namelist()

    def read_bytes(self, path: str) -> bytes:
        return self._archive.read(path)

    def write_bytes(self, path: str, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")

    def remove(self, path: str, *, force: bool = False) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")

    def rename(self, old_path: str, new_path: str) -> None:  # pragma: no cover
        raise NotImplementedError("writing ZIP archives is not supported")


class Zip(Filesystem):
    """ZIP — archives that may carry Acorn files (SparkFS extras, RISC OS types).

    Detected by the unambiguous ``PK`` signature. This identifies and
    reads the container; whether it holds Acorn files, and their
    metadata, is the concern of this package's archive API.
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
