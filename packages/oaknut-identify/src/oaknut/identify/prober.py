"""The prober extension axis: the contract every format detector implements.

A :class:`Prober` is an :class:`~oaknut.extension.Extension` on the
``oaknut.prober`` namespace. Each one inspects an image's bytes and
emits :class:`Identification` candidates with a :class:`Confidence`
level and supporting evidence. The :func:`~oaknut.identify.identify`
coordinator runs the whole registered cascade and ranks the results.
"""

from __future__ import annotations

import enum
from abc import abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field

from oaknut.discimage import DiscFormat
from oaknut.extension import Extension, namespace_for
from oaknut.identify.reader import ImageReader

#: The extension *kind* (axis) these plug-ins belong to.
PROBER_KIND = "prober"

#: The entry-point namespace probers register under: ``"oaknut.prober"``.
PROBER_NAMESPACE = namespace_for(PROBER_KIND)


class Confidence(enum.IntEnum):
    """How sure a prober is, ordered so higher means more certain.

    The cascade ranks candidates by this first, so an unambiguous magic
    number always beats a structural heuristic, which beats a guess
    from size alone.
    """

    #: Only weak signals agree — image size, or nothing but the extension.
    POSSIBLE = 10
    #: Structural heuristics pass (e.g. a well-formed DFS catalogue).
    PROBABLE = 20
    #: Heuristics plus an integrity check agree (checksum, redundant copy).
    STRONG = 30
    #: An unambiguous on-disc magic number was found (e.g. ``AFS0``).
    CERTAIN = 40


@dataclass(frozen=True)
class Identification:
    """One candidate answer to "what format is this image?".

    A prober may emit several (ranked by the coordinator), and an image
    may legitimately yield more than one — a single physical image can
    carry, say, an ADFS host with an AFS tail partition.
    """

    #: Entry-point name of the prober that produced this candidate.
    prober_name: str
    #: Coarse routing family — ``"dfs"``, ``"adfs"``, ``"afs"``, ``"zip"``, …
    family: str
    #: How sure the prober is.
    confidence: Confidence
    #: Human-readable reasons this candidate matched.
    evidence: tuple[str, ...] = ()
    #: The concrete format when geometry/layout is determinable, else None.
    disc_format: DiscFormat | None = None
    #: Equally-plausible formats that the content cannot distinguish from
    #: :attr:`disc_format` (e.g. interleaved vs. sequential double-sided).
    alternatives: tuple[DiscFormat, ...] = ()
    #: Sub-formats found nested within this one (e.g. an AFS tail on an
    #: ADFS host).
    contained: tuple["Identification", ...] = field(default_factory=tuple)


class Prober(Extension):
    """Base class for disc-image format detectors.

    Subclasses set :attr:`family`, declare the extensions they are
    conventionally associated with (used only for tie-breaking), and
    implement :meth:`probe`. They are registered under the
    ``oaknut.prober`` namespace::

        [project.entry-points."oaknut.prober"]
        acorn_dfs = "oaknut.dfs.probers:AcornDFSProber"
    """

    #: Coarse routing family this prober identifies.
    family: str = ""
    #: Extensions conventionally used for this format (lower-case, with
    #: leading dot). Consulted by the coordinator only to break ties
    #: between equally-confident candidates — never to identify.
    extensions: frozenset[str] = frozenset()
    #: Ordering hint among same-confidence, same-extension candidates;
    #: higher wins. Most probers can leave this at zero.
    priority: int = 0

    @classmethod
    def _kind(cls) -> str:
        return PROBER_KIND

    @abstractmethod
    def probe(self, reader: ImageReader) -> Iterable[Identification]:
        """Inspect *reader* and yield zero or more :class:`Identification`.

        Implementations read only what they need via
        :meth:`ImageReader.read`, tolerate short reads (the image may be
        truncated), and must not raise on data that simply isn't their
        format — they return no candidates instead.
        """
        raise NotImplementedError
