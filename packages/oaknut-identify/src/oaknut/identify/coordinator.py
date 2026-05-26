"""The identification cascade: run every registered prober and rank the results.

:func:`identify` is the entry point. The per-axis helpers
(:func:`prober_names`, :func:`describe_prober`, :func:`create_prober`)
mirror the convenience layer every oaknut extension axis grows on top
of :mod:`oaknut.extension`.
"""

from __future__ import annotations

import stevedore
from oaknut.extension import (
    create_extension,
    describe_extension,
    list_extensions,
    load_failure_callback,
)
from oaknut.identify.prober import (
    PROBER_KIND,
    PROBER_NAMESPACE,
    Identification,
    Prober,
)
from oaknut.identify.reader import ImageSource, reader_for

__all__ = [
    "identify",
    "prober_names",
    "describe_prober",
    "create_prober",
]


def prober_names() -> list[str]:
    """The entry-point names of every registered prober."""
    return list_extensions(PROBER_NAMESPACE)


def describe_prober(name: str, *, single_line: bool = False) -> str:
    """The description of one prober (its class docstring)."""
    return describe_extension(
        PROBER_KIND, PROBER_NAMESPACE, name, single_line=single_line
    )


def create_prober(name: str) -> Prober:
    """Instantiate one prober by name."""
    return create_extension(kind=PROBER_KIND, namespace=PROBER_NAMESPACE, name=name)


def _registered_probers() -> dict[str, Prober]:
    """Instantiate every registered prober, keyed by entry-point name."""
    manager = stevedore.ExtensionManager(
        namespace=PROBER_NAMESPACE,
        invoke_on_load=False,
        on_load_failure_callback=load_failure_callback,
    )
    return {ext.name: ext.plugin(name=ext.name) for ext in manager}


def identify(
    source: ImageSource, *, suffix_hint: str | None = None
) -> list[Identification]:
    """Identify the disc-image format(s) of *source*, best candidate first.

    Runs the whole registered prober cascade over the image and returns
    the candidates ranked by confidence, with the file extension used
    only to break ties between equally-confident results. An empty list
    means no prober recognised the content.

    Args:
        source: A path, an in-memory buffer, or an :class:`ImageReader`.
        suffix_hint: Override the extension used for tie-breaking (handy
            when *source* is a buffer, or a path whose name lies).

    Returns:
        Ranked :class:`Identification` candidates (possibly empty).
    """
    with reader_for(source, suffix_hint=suffix_hint) as reader:
        probers = _registered_probers()
        candidates: list[Identification] = []
        for prober in probers.values():
            candidates.extend(prober.probe(reader))
        return _rank(candidates, probers, reader.suffix)


def _rank(
    candidates: list[Identification],
    probers: dict[str, Prober],
    suffix: str | None,
) -> list[Identification]:
    """Order *candidates* best-first.

    Primary key is confidence; ties are broken by whether the file
    extension agrees with the candidate's prober, then the prober's
    declared priority, and finally the prober name for determinism.
    """

    def extension_agrees(ident: Identification) -> bool:
        prober = probers.get(ident.prober_name)
        return bool(suffix and prober and suffix in prober.extensions)

    def priority(ident: Identification) -> int:
        prober = probers.get(ident.prober_name)
        return prober.priority if prober is not None else 0

    # Two-stage stable sort: name ascending, then the descending rank
    # tuple. Ties therefore settle on name-ascending order.
    ordered = sorted(candidates, key=lambda i: i.prober_name)
    ordered.sort(
        key=lambda i: (int(i.confidence), extension_agrees(i), priority(i)),
        reverse=True,
    )
    return ordered
