"""The image-decoder extension axis.

Most disc images are sector images: the bytes of each sector in order,
which a filesystem can read directly. Some image formats record a disc
at a lower level. An HFE file, for instance, holds the flux bitstream of
every track. An :class:`ImageDecoder` recognises such a format and decodes
it into the sector image the filesystems expect.

Decoders register on the ``oaknut.decoder`` entry-point axis::

    [project.entry-points."oaknut.decoder"]
    hfe = "oaknut.hfe.decoder:HFEDecoder"

:func:`~oaknut.filesystem.reader_for` consults them, so identification
and mounting see the decoded image without knowing a decoder was
involved. A decoded image is read-only: it is a reconstruction of the
original, and there is nothing to write changes back into.
"""

from __future__ import annotations

import functools
from abc import abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import stevedore
from oaknut.extension import Extension, load_failure_callback, namespace_for

__all__ = [
    "DECODER_KIND",
    "DECODER_NAMESPACE",
    "DecodedImage",
    "ImageDecoder",
    "PREFIX_LENGTH",
    "decoder_for",
    "registered_decoders",
    "decode_filepath",
    "clear_decode_cache",
]

#: The extension *kind* (axis) image decoders belong to.
DECODER_KIND = "decoder"

#: The entry-point namespace decoders register under: ``"oaknut.decoder"``.
DECODER_NAMESPACE = namespace_for(DECODER_KIND)

#: How many leading bytes of an image :meth:`ImageDecoder.recognises` sees.
PREFIX_LENGTH = 512

_CACHE_SIZE = 4


@dataclass(frozen=True)
class DecodedImage:
    """A sector image decoded from some other image format."""

    data: bytes
    #: The conventional extension for a sector image of this shape, used as
    #: the identification tie-break hint in place of the source's own.
    suffix: str | None
    #: The source format, for messages (``"HFE v3"``).
    format_name: str
    #: Remarks on the decoding a user should see, such as unreadable sectors.
    notes: tuple[str, ...] = ()


class ImageDecoder(Extension):
    """Base class for a pluggable image decoder.

    A subclass recognises its format from the first :data:`PREFIX_LENGTH`
    bytes of an image (a magic number, typically) and decodes the whole
    image into a :class:`DecodedImage`.
    """

    #: Extensions conventionally used for this format (lower-case, with
    #: leading dot), for documentation; recognition is by content.
    extensions: frozenset[str] = frozenset()

    @classmethod
    def _kind(cls) -> str:
        return DECODER_KIND

    @abstractmethod
    def recognises(self, prefix: bytes) -> bool:
        """Whether an image starting with *prefix* is in this format."""
        raise NotImplementedError

    @abstractmethod
    def decode(self, data: bytes) -> DecodedImage:
        """The sector image decoded from the whole image *data*.

        Raises:
            DataError: *data* is in this format but cannot be decoded.
        """
        raise NotImplementedError


@functools.cache
def registered_decoders() -> dict[str, ImageDecoder]:
    """Every registered decoder, keyed by entry-point name."""
    manager = stevedore.ExtensionManager(
        namespace=DECODER_NAMESPACE,
        invoke_on_load=False,
        on_load_failure_callback=load_failure_callback,
    )
    return {ext.name: ext.plugin(name=ext.name) for ext in manager}


def decoder_for(
    prefix: bytes, decoders: dict[str, ImageDecoder] | None = None
) -> ImageDecoder | None:
    """The decoder that recognises an image starting with *prefix*, if any."""
    active = registered_decoders() if decoders is None else decoders
    for decoder in active.values():
        if decoder.recognises(prefix[:PREFIX_LENGTH]):
            return decoder
    return None


_cache: OrderedDict[tuple, DecodedImage] = OrderedDict()


def decode_filepath(filepath: Path, decoder: ImageDecoder) -> DecodedImage:
    """Decode the file at *filepath* with *decoder*, reusing a recent result.

    Decoding can take a noticeable fraction of a second, and one command
    may open the same image several times (to identify it, then to mount
    it), so the last few results are kept while the file is unchanged.
    """
    stat = filepath.stat()
    key = (str(filepath.resolve()), stat.st_mtime_ns, stat.st_size, decoder.name, id(decoder))
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    decoded = decoder.decode(filepath.read_bytes())
    _cache[key] = decoded
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return decoded


def clear_decode_cache() -> None:
    """Forget every cached decoding."""
    _cache.clear()
