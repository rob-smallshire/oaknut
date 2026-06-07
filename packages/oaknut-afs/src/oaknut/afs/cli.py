"""AFS contributed ``disc`` commands.

The ``disc afs`` command group, contributed to the CLI on the
``oaknut.command`` axis (see ``docs/dev/contributed-commands.md``). It
holds the Level 3 File Server administration that does not fit the
generic mount model: partitioning and initialising the AFS region inside
an ADFS disc, planning that, and managing users and passwords —
``disc afs init`` / ``plan`` / ``users`` / ``useradd`` / ``userdel`` /
``passwd`` / ``merge``.

This module imports Click and is loaded only when ``oaknut-afs`` is
installed with its ``[cli]`` extra; the AFS library core never imports it.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import click
from asyoulikeit import ByAudience
from asyoulikeit.cli import report_output
from oaknut.cli import kv_table
from oaknut.file.capacity import format_capacity


@click.group()
def afs() -> None:
    """Acorn Level 3 File Server (AFS) administration."""


# ---------------------------------------------------------------------------
# Image openers — AFS lives in the tail of an ADFS disc, so these admin
# commands open the ADFS host and reach the AFS partition through it.
# ---------------------------------------------------------------------------


@contextmanager
def _adfs_from_file(image_filepath: Path) -> Iterator:
    """Open an ADFS image, translating stdlib OS errors into categorised ones.

    :meth:`ADFS.from_file` raises :class:`FileNotFoundError` when an
    ADFS hard-disc ``.dat`` is missing its companion ``.dsc`` (or
    vice versa). That stdlib error bypasses the CLI's
    :func:`handled_errors` boundary and prints a raw traceback — a
    bug from the user's point of view. Re-raise the same message
    through :class:`ADFSError` so it flows through the categorised
    error pipeline and emerges as a normal ``Error: …`` line.
    """
    from oaknut.adfs import ADFS
    from oaknut.adfs.exceptions import ADFSError

    try:
        with ADFS.from_file(image_filepath) as adfs_disc:
            yield adfs_disc
    except FileNotFoundError as exc:
        # Bare raise (no ``from exc``) so render_error does not echo
        # the same message twice as a "caused by" line — the cause
        # chain still threads through ``__context__`` for --debug.
        raise ADFSError(str(exc)) from None


@contextmanager
def _open_afs(image_filepath: Path) -> Iterator:
    """Open image as ADFS, grab the AFS partition, yield it.

    Raises :class:`AFSNotPresentError` if no AFS partition is
    installed; the CLI :func:`handled_errors` boundary translates
    that to a user-facing message and exit code.
    """
    with (
        _adfs_from_file(image_filepath) as adfs_disc,
        adfs_disc.open_afs_partition() as afs_region,
    ):
        yield afs_region


@contextmanager
def _open_for_afs_write(image_filepath: Path) -> Iterator:
    """Open for AFS write: yields (adfs, afs) with auto-flush on clean exit."""
    with (
        _adfs_from_file(image_filepath) as adfs_disc,
        adfs_disc.open_afs_partition() as afs_region,
    ):
        yield adfs_disc, afs_region


def _navigate_afs(afs_region, bare_path: str):
    """Navigate AFS using its root / operator since AFS.path() may not exist."""
    if bare_path == "$" or not bare_path:
        return afs_region.root
    # Strip leading "$."
    if bare_path.startswith("$."):
        bare_path = bare_path[2:]
    elif bare_path == "$":
        return afs_region.root
    target = afs_region.root
    for part in bare_path.split("."):
        target = target / part
    return target


# ---------------------------------------------------------------------------
# afs plan
# ---------------------------------------------------------------------------


@afs.command(name="plan")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--cylinders",
    type=int,
    default=None,
    help="Proposed AFS region size in cylinders.",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="Plan with ADFS compaction to maximise AFS space.",
)
@report_output(
    reports={
        "geometry": "Disc geometry.",
        "adfs_state": "ADFS occupancy.",
        "existing_afs": "Existing AFS partition (only when one is already installed).",
        "plan": "Proposed new AFS partition (only when computable).",
    }
)
def plan(
    image: Path,
    cylinders: int | None,
    compact: bool,
):
    """Show what ``afs init`` would do, without modifying the image.

    By default, plans using the existing tail free extent (matching
    WFSINIT behaviour). With --compact, plans a compaction-first
    layout that reclaims the maximum space. With --cylinders N,
    shows the plan for that specific size. Reports disc geometry,
    current ADFS occupancy, whether compaction is needed, and the
    resulting partition layout.

    Use ``--as json`` to emit a machine-readable document instead
    of the human-readable display report.
    """
    from oaknut.adfs import ADFS
    from oaknut.afs.wfsinit import AFSSizeSpec
    from oaknut.afs.wfsinit.partition import plan as plan_partition

    with ADFS.from_file(image) as adfs_disc:
        geom = adfs_disc.geometry
        total_sectors = geom.total_sectors
        free_bytes = adfs_disc.free_space
        free_sectors = free_bytes // 256
        used_sectors = total_sectors - free_sectors

        document: dict = {
            "image": str(image),
            "geometry": {
                "cylinders": geom.cylinders,
                "heads": geom.heads,
                "sectors_per_track": geom.sectors_per_track,
                "total_sectors": total_sectors,
                "total_bytes": total_sectors * 256,
            },
            "adfs": {
                "used_sectors": used_sectors,
                "free_sectors": free_sectors,
                "free_bytes": free_bytes,
            },
        }

        # Check for existing AFS partition.
        sec1, sec2 = adfs_disc._fsm.afs_info_pointers
        if sec1 != 0 or sec2 != 0:
            existing: dict = {"present": True}
            if adfs_disc.has_afs_partition:
                afs_region = adfs_disc.afs_partition
                existing["disc_name"] = afs_region.disc_name
                existing["start_cylinder"] = afs_region.start_cylinder
            document["existing_afs"] = existing
            return _build_afs_plan_reports(document)

        document["existing_afs"] = {"present": False}

        # Compute the plan using the same defaults as afs init:
        # existing_free() without compaction (matching WFSINIT), or
        # max() with compaction when --compact is given.
        if cylinders:
            size = AFSSizeSpec.cylinders(cylinders)
        elif compact:
            size = AFSSizeSpec.max()
        else:
            size = AFSSizeSpec.existing_free()
        try:
            p = plan_partition(adfs_disc, size=size, compact_adfs=compact)
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc

        document["plan"] = {
            "afs_cylinders": p.afs_cylinders,
            "total_afs_sectors": p.total_afs_sectors,
            "total_afs_bytes": p.total_afs_sectors * 256,
            "start_cylinder": p.start_cylinder,
            "new_adfs_cylinders": p.new_adfs_cylinders,
            "will_compact": p.will_compact,
            "compact_requested": compact,
            "cylinders_requested": cylinders,
        }

        if not cylinders:
            compact_flag = " --compact" if compact else ""
            document["suggested_command"] = (
                f"disc afs init {image} --disc-name NAME"
                f" --cylinders {p.afs_cylinders}{compact_flag}"
            )

        return _build_afs_plan_reports(document)


def _build_afs_plan_reports(document: dict):
    """Build a Reports collection from the afs plan document dict.

    One report per document section: ``geometry``, ``adfs_state``,
    optionally ``existing_afs`` (only when an AFS partition is
    already installed) or ``plan`` (only when computed).  The
    transposed single-row table shape turns each section into a
    key-value block in display mode and ``field\\tvalue`` lines in
    TSV.
    """
    from asyoulikeit.tabular_data import Report, Reports

    sections: dict = {}
    geom = document["geometry"]
    sections["geometry"] = Report(
        data=kv_table(
            "Disc geometry",
            [
                (
                    "shape",
                    "Shape",
                    f"{geom['cylinders']} cylinders, "
                    f"{geom['heads']} heads, "
                    f"{geom['sectors_per_track']} sectors/track",
                ),
                (
                    "total",
                    "Total",
                    f"{geom['total_sectors']} sectors ({geom['total_bytes']:,} bytes)",
                ),
            ],
        )
    )

    adfs_state = document["adfs"]
    sections["adfs_state"] = Report(
        data=kv_table(
            "ADFS occupancy",
            [
                ("used_sectors", "Used sectors", str(adfs_state["used_sectors"])),
                ("free_sectors", "Free sectors", str(adfs_state["free_sectors"])),
                ("free_bytes", "Free bytes", f"{adfs_state['free_bytes']:,}"),
            ],
        )
    )

    existing = document["existing_afs"]
    if existing["present"]:
        pairs = [("present", "Present", "yes")]
        if "disc_name" in existing:
            pairs.append(("disc_name", "Disc name", existing["disc_name"]))
            pairs.append(("start_cylinder", "Start cylinder", str(existing["start_cylinder"])))
        sections["existing_afs"] = Report(data=kv_table("Existing AFS partition", pairs))
        return Reports(sections)

    p = document["plan"]
    plan_pairs = [
        (
            "afs_region",
            "AFS region",
            f"{p['afs_cylinders']} cylinders "
            f"({p['total_afs_sectors']} sectors, "
            f"{p['total_afs_bytes']:,} bytes)",
        ),
        ("start_cylinder", "Start cylinder", str(p["start_cylinder"])),
        ("new_adfs_cylinders", "ADFS retained", f"{p['new_adfs_cylinders']} cylinders"),
        (
            "will_compact",
            "Compaction",
            "required" if p["will_compact"] else "not required",
        ),
    ]
    if "suggested_command" in document:
        plan_pairs.append(("suggested_command", "Suggested command", document["suggested_command"]))
    sections["plan"] = Report(data=kv_table("Proposed AFS partition", plan_pairs))
    return Reports(sections)


# ---------------------------------------------------------------------------
# afs init
# ---------------------------------------------------------------------------


@afs.command(name="init")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option("--disc-name", required=True, help="AFS disc name.")
@click.option(
    "--cylinders",
    type=int,
    default=None,
    help="AFS region size in cylinders (default: use existing free space).",
)
@click.option(
    "--compact",
    is_flag=True,
    default=False,
    help="Compact the ADFS partition first to maximise AFS space.",
)
@click.option(
    "--user",
    "users",
    multiple=True,
    help=(
        "User spec as NAME, NAME:S (system), NAME:QUOTA, "
        "or NAME:S:QUOTA. Quota accepts e.g. 2MiB. Repeat for multiple. "
        "A NAME matching a built-in (Syst, Boot, Welcome) overrides "
        "that built-in's quota; Syst requires :S. Set passwords with "
        "--user-password, not here."
    ),
)
@click.option(
    "--user-password",
    "user_passwords",
    multiple=True,
    metavar="NAME=VALUE",
    help=(
        "Set a user's password as NAME=VALUE, split once on the first "
        "'=' so the password may itself contain ':' or '='. NAME must "
        "match a --user or a built-in (Syst, Boot, Welcome). Repeat for "
        "multiple. Passwords are stored as cleartext (max 6 ASCII chars)."
    ),
)
@click.option(
    "--default-quota",
    default=None,
    help="Default quota for users without an explicit quota (e.g. 256KiB).",
)
@click.option(
    "--omit-user",
    "omit_users",
    multiple=True,
    help="Suppress a built-in account (Syst, Boot, or Welcome). Repeat for multiple.",
)
@click.option(
    "--emplace",
    "emplacements",
    multiple=True,
    help=(
        "Emplace a library: a shipped name (Library, Library1, ArthurLib, "
        "Utils), the literal 'all' to emplace every shipped library, or a "
        "path to an ADFS .adl image. Repeat for multiple."
    ),
)
def init(
    image: Path,
    disc_name: str,
    cylinders: int | None,
    compact: bool,
    users: tuple[str, ...],
    user_passwords: tuple[str, ...],
    default_quota: str | None,
    omit_users: tuple[str, ...],
    emplacements: tuple[str, ...],
) -> None:
    """Initialise an AFS partition on an ADFS hard disc image."""
    from oaknut.adfs import ADFS
    from oaknut.afs.exceptions import AFSInitSpecError
    from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise

    try:
        user_specs: list[UserSpec] = _parse_user_specs(users)
        user_specs = _apply_user_passwords(user_specs, user_passwords)

        init_kwargs: dict = {
            "disc_name": disc_name,
            "users": user_specs,
            "omit_builtins": frozenset(omit_users),
        }
        if cylinders:
            init_kwargs["size"] = AFSSizeSpec.cylinders(cylinders)
        if compact:
            init_kwargs["compact_adfs"] = True
            # When compacting, default to max space unless cylinders given.
            if "size" not in init_kwargs:
                init_kwargs["size"] = AFSSizeSpec.max()
        if default_quota is not None:
            from oaknut.file.capacity import parse_capacity

            try:
                init_kwargs["default_quota"] = parse_capacity(default_quota)
            except ValueError as exc:
                raise click.ClickException(str(exc)) from exc

        spec = InitSpec(**init_kwargs)
    except AFSInitSpecError as exc:
        raise click.ClickException(str(exc)) from exc

    with ADFS.from_file(image) as adfs_disc:
        initialise(adfs_disc, spec=spec)

        # Emplace libraries after initialisation so we can report
        # replacements to the user.
        if emplacements:
            from oaknut.afs.libraries import emplace_library

            with adfs_disc.open_afs_partition() as afs_region:
                for name in _expand_emplacements(emplacements):
                    try:
                        replaced = emplace_library(afs_region, name)
                    except (ValueError, FileNotFoundError) as exc:
                        raise click.ClickException(str(exc)) from exc
                    if replaced:
                        for fname in replaced:
                            click.echo(f"  replaced $.{name}/{fname}", err=True)


def _expand_emplacements(emplacements: tuple[str, ...]) -> list[str]:
    """Expand the ``all`` pseudo-name to every shipped library.

    Other values pass through unchanged, in their original order, so
    ``--emplace Library --emplace all --emplace /path/Custom.adl``
    yields ``[Library, *SHIPPED_LIBRARIES, /path/Custom.adl]`` —
    duplicates are preserved and the per-call conflict semantics in
    :func:`emplace_library` resolve them on disc.
    """
    from oaknut.afs.libraries import SHIPPED_LIBRARIES

    expanded: list[str] = []
    for name in emplacements:
        if name == "all":
            expanded.extend(SHIPPED_LIBRARIES)
        else:
            expanded.append(name)
    return expanded


def _parse_user_specs(raw_specs: tuple[str, ...]) -> list:
    """Parse user specs from command-line strings.

    Accepted forms::

        NAME            — plain user
        NAME:S          — system user
        NAME:2MiB       — user with explicit quota
        NAME:S:2MiB     — system user with explicit quota
    """
    from oaknut.afs.wfsinit import UserSpec
    from oaknut.file.capacity import parse_capacity

    specs: list[UserSpec] = []
    for raw in raw_specs:
        parts = raw.split(":")
        name = parts[0]
        system = False
        quota = None
        for part in parts[1:]:
            if part.upper() == "S":
                system = True
            else:
                try:
                    quota = parse_capacity(part)
                except ValueError as exc:
                    raise click.ClickException(
                        f"unrecognised user spec component '{part}' in '{raw}'"
                    ) from exc
        kwargs: dict = {"name": name, "system": system}
        if quota is not None:
            kwargs["quota"] = quota
        specs.append(UserSpec(**kwargs))
    return specs


def _apply_user_passwords(user_specs: list, raw_passwords: tuple[str, ...]) -> list:
    """Merge ``--user-password NAME=VALUE`` specs into ``user_specs``.

    Each raw string is split **once** on the first ``=``: the left side
    is the user name (the constrained key) and the right side is the
    password, taken verbatim — so it may itself contain ``:`` or ``=``.
    A name matching an existing ``--user`` spec sets that spec's
    password; a name matching a built-in (Syst/Boot/Welcome) synthesises
    an override spec with the built-in's required system flag; any other
    name is an error.
    """
    if not raw_passwords:
        return user_specs

    import dataclasses

    from oaknut.afs.passwords import normalise_username
    from oaknut.afs.wfsinit import (
        BUILTIN_ACCOUNT_NAMES,
        UserSpec,
        builtin_account_system_flag,
    )

    builtin_by_key = {normalise_username(n): n for n in BUILTIN_ACCOUNT_NAMES}
    spec_index_by_key = {normalise_username(spec.name): i for i, spec in enumerate(user_specs)}
    specs = list(user_specs)
    seen: set[str] = set()

    for raw in raw_passwords:
        name, separator, password = raw.partition("=")
        if not separator:
            raise click.ClickException(f"--user-password must be NAME=VALUE, got {raw!r}")
        if not name:
            raise click.ClickException(f"--user-password has an empty user name: {raw!r}")
        key = normalise_username(name)
        if key in seen:
            raise click.ClickException(f"duplicate --user-password for {name!r}")
        seen.add(key)

        if key in spec_index_by_key:
            index = spec_index_by_key[key]
            specs[index] = dataclasses.replace(specs[index], password=password)
        elif key in builtin_by_key:
            canonical = builtin_by_key[key]
            specs.append(
                UserSpec(
                    name=canonical,
                    password=password,
                    system=builtin_account_system_flag(canonical),
                )
            )
            spec_index_by_key[key] = len(specs) - 1
        else:
            raise click.ClickException(
                f"--user-password names {name!r}, which is neither a --user "
                f"nor a built-in account ({', '.join(sorted(BUILTIN_ACCOUNT_NAMES))})"
            )
    return specs


# ---------------------------------------------------------------------------
# afs users / useradd / userdel / passwd
# ---------------------------------------------------------------------------


@afs.command(name="users")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@report_output(reports={"users": "Users with system flag and quota."})
def users(image: Path):
    """List AFS users with quota and flags."""
    from asyoulikeit.tabular_data import Report, Reports, TableContent

    table = TableContent(title="users")
    table.add_column("user", "User", header=True)
    table.add_column("system", "System")
    table.add_column("quota", "Quota")

    with _open_afs(image) as afs_region:
        for u in afs_region.users.active:
            table.add_row(
                user=u.full_id,
                system="yes" if u.is_system else "",
                # A quota is a byte count: humans want friendly units,
                # machines want the raw number. ByAudience carries both,
                # and the selected formatter's audience picks one.
                quota=ByAudience(
                    machine=u.free_space,
                    human=format_capacity(u.free_space),
                ),
            )
    return Reports(users=Report(data=table))


@afs.command(name="useradd")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
@click.option("--system", is_flag=True, help="System user flag.")
@click.option("--quota", type=int, default=None, help="Quota in bytes.")
@click.option("--password", default="", help="Initial password.")
def useradd(
    image: Path,
    name: str,
    system: bool,
    quota: int | None,
    password: str,
) -> None:
    """Add a user to the AFS passwords file."""
    with _open_for_afs_write(image) as (_adfs_disc, afs_region):
        afs_region.add_user(
            name,
            system=system,
            password=password,
            quota=quota or 0,
        )


@afs.command(name="userdel")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
def userdel(image: Path, name: str) -> None:
    """Remove a user from the AFS passwords file."""
    with _open_for_afs_write(image) as (_adfs_disc, afs_region):
        afs_region.remove_user(name)


@afs.command(name="passwd")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.argument("name")
@click.option("--password", required=True, help="New password (max 6 ASCII chars).")
def passwd(image: Path, name: str, password: str) -> None:
    """Change an existing AFS user's login password.

    The Level 3 File Server stores passwords as up to six cleartext
    ASCII characters; there is no encryption. Unlike ``afs useradd`` this
    only rewrites an existing record in place, so it never grows the
    passwords file.
    """
    with _open_for_afs_write(image) as (_adfs_disc, afs_region):
        afs_region.set_password(name, password)


# ---------------------------------------------------------------------------
# afs merge
# ---------------------------------------------------------------------------


@afs.command(name="merge")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Source AFS image to merge from.",
)
@click.option("--target-path", default=None, help="Target AFS path for merge root.")
@click.option(
    "--on-conflict",
    type=click.Choice(["error", "skip", "overwrite"], case_sensitive=False),
    default="error",
    show_default=True,
    help="Policy when a source entry's name already exists on the target.",
)
def merge(
    image: Path,
    source: Path,
    target_path: str | None,
    on_conflict: str,
) -> None:
    """Bulk-copy the AFS file tree from one image into another.

    Walks the source AFS partition recursively and recreates every
    directory and file under the target's AFS partition, preserving
    each entry's access byte, load address, exec address, and date.
    The source image is opened read-only; only the target is mutated.

    Typical uses:

    \b
      - layering a shipped library image (``Library``, ``ArthurLib``,
        ``Library1``) onto a server disc after the fact, when
        ``afs init --emplace`` was not used at creation time;
      - consolidating two Level 3 File Server discs onto one image,
        either at the AFS root or — with ``--target-path`` — under a
        chosen subdirectory of the target's namespace.

    The ``Passwords`` file is always excluded so the target's own
    user records survive intact.

    The ``--on-conflict`` policy chooses what happens when a source
    entry's name already exists on the target:

    \b
      - ``error`` (default): abort the whole merge before writing
        anything, so no partial state lands on disc;
      - ``skip``: keep the target's existing entry, drop the source's;
      - ``overwrite``: replace the target's entry with the source's
        (the old bytes are released back to the allocator).
    """
    from oaknut.adfs import ADFS
    from oaknut.afs import merge as merge_trees

    with (
        ADFS.from_file(image) as target_adfs,
        target_adfs.open_afs_partition() as target_afs,
        ADFS.from_file(source) as source_adfs,
        source_adfs.open_afs_partition() as source_afs,
    ):
        target_root = target_afs.root
        if target_path:
            target_root = _navigate_afs(target_afs, target_path)

        merge_trees(
            target_afs,
            source_afs,
            target_path=target_root,
            conflict=on_conflict.lower(),
        )
