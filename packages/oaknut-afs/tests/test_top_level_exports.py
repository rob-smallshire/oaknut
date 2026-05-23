"""Re-exports of the wfsinit building blocks from oaknut.afs (#31)."""

from __future__ import annotations


def test_init_names_are_reachable_from_top_level() -> None:
    """``initialise``, ``InitSpec``, ``AFSSizeSpec``, ``UserSpec``,
    and ``emplace_library`` all importable from ``oaknut.afs`` directly.
    """
    from oaknut.afs import (  # noqa: F401
        AFSSizeSpec,
        InitSpec,
        UserSpec,
        emplace_library,
        initialise,
    )


def test_repartition_plan_reachable() -> None:
    """``RepartitionPlan`` is the canonical plan/apply contract — also
    surface it at top level so callers do not have to know it lives
    inside ``wfsinit.partition``.
    """
    from oaknut.afs import RepartitionPlan  # noqa: F401


def test_lower_level_paths_still_work() -> None:
    """The internal submodule paths remain valid (no removals)."""
    from oaknut.afs.libraries import emplace_library  # noqa: F401
    from oaknut.afs.wfsinit import (  # noqa: F401
        AFSSizeSpec,
        InitSpec,
        UserSpec,
        initialise,
    )
