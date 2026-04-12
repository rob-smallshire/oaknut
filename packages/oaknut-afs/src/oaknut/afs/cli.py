"""Thin CLI for oaknut-afs.

Phase 21 of the oaknut-afs build. Exposes the most common disc
inspection and mutation operations as subcommands of an
``oaknut-afs-disc`` (or equivalent) entry point. Not a complete
replacement for the forthcoming ``disc`` multi-filesystem tool —
this is a focused, standalone surface for scripting and CI use
while that tool is in flight.

Subcommands:

- ``info PATH`` — print disc metadata (name, geometry, start
  cylinder, free sectors, user list).
- ``ls PATH [AFSPATH]`` — list entries under the given AFS path,
  defaulting to the root.
- ``cat PATH AFSPATH`` — stream a file's bytes to stdout.
- ``put PATH AFSPATH LOCALFILE`` — write bytes from ``LOCALFILE``
  into the AFS path (creates / replaces).
- ``initialise PATH --disc-name NAME [--cylinders N] [--user ...]``
  — run :func:`oaknut.afs.wfsinit.initialise` on an ADFS disc
  image to create a fresh AFS region.

All subcommands operate on an ADFS disc image path (.adl / .dat /
.adf) and open it via ``ADFS.from_file`` with the correct mode
for the operation (read-only for info/ls/cat, writable for put /
initialise).

Invoked as ``python -m oaknut.afs.cli`` when no console-scripts
entry is configured.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from oaknut.adfs import ADFS
from oaknut.afs import AFSPath
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise


def _open_adfs_ro(path: Path):
    return ADFS.from_file(path)


def _open_adfs_rw(path: Path):
    return ADFS.from_file(path, mode="r+b")


def _parse_afs_path(text: str) -> AFSPath:
    return AFSPath.parse(text)


def cmd_info(args: argparse.Namespace) -> int:
    with _open_adfs_ro(args.path) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            print(f"{args.path}: no AFS partition")
            return 1
        print(f"disc name:      {afs.disc_name}")
        print(f"start cylinder: {afs.start_cylinder}")
        geom = afs.geometry
        print(f"cylinders:      {geom.cylinders}")
        print(f"sectors/cyl:    {geom.sectors_per_cylinder}")
        print(f"total sectors:  {geom.total_sectors}")
        print(f"free sectors:   {afs.free_sectors}")
        print("users:")
        for u in afs.users.active:
            flags = "S" if u.is_system else " "
            print(f"  {flags} {u.full_id:20s} quota={u.free_space:#010x}")
    return 0


def cmd_ls(args: argparse.Namespace) -> int:
    with _open_adfs_ro(args.path) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            print(f"{args.path}: no AFS partition", file=sys.stderr)
            return 1
        target = afs.root
        if args.afs_path and args.afs_path != "$":
            target = afs.root / _strip_root(args.afs_path)
            target = _rebind(target, afs)
        if not target.exists() and not target.is_root():
            print(f"{args.afs_path}: no such path", file=sys.stderr)
            return 1
        if target.is_file():
            print(target.name)
            return 0
        for child in target:
            marker = "d" if child.is_dir() else "-"
            entry = child.stat()
            print(f"{marker} {entry.name:12s} {entry.sin:08x}")
    return 0


def _strip_root(text: str) -> str:
    if text.startswith("$."):
        return text[2:]
    if text == "$":
        return ""
    return text


def _rebind(path: AFSPath, afs) -> AFSPath:
    """Re-bind a path's parts to a specific AFS handle."""
    out = afs.root
    for part in path.parts[1:]:
        out = out / part
    return out


def cmd_cat(args: argparse.Namespace) -> int:
    with _open_adfs_ro(args.path) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            print(f"{args.path}: no AFS partition", file=sys.stderr)
            return 1
        target = afs.root
        for part in _parse_afs_path(args.afs_path).parts[1:]:
            target = target / part
        sys.stdout.buffer.write(target.read_bytes())
    return 0


def cmd_put(args: argparse.Namespace) -> int:
    with _open_adfs_rw(args.path) as adfs:
        afs = adfs.afs_partition
        if afs is None:
            print(f"{args.path}: no AFS partition", file=sys.stderr)
            return 1
        data = Path(args.local_file).read_bytes()
        target = afs.root
        for part in _parse_afs_path(args.afs_path).parts[1:]:
            target = target / part
        target.write_bytes(
            data,
            load_address=args.load,
            exec_address=args.exec_,
        )
        afs.flush()
    return 0


def cmd_initialise(args: argparse.Namespace) -> int:
    users: list[UserSpec] = []
    for user_spec in args.user or []:
        parts = user_spec.split(":")
        name = parts[0]
        flags = parts[1] if len(parts) > 1 else ""
        users.append(
            UserSpec(
                name=name,
                system="S" in flags,
            )
        )

    omit_builtins = frozenset(args.omit_user or [])

    if args.cylinders:
        size = AFSSizeSpec.cylinders(args.cylinders)
    else:
        size = AFSSizeSpec.max()

    with _open_adfs_rw(args.path) as adfs:
        initialise(
            adfs,
            spec=InitSpec(
                disc_name=args.disc_name,
                size=size,
                users=users,
                omit_builtins=omit_builtins,
            ),
        )
    print(f"initialised AFS region on {args.path}")
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="oaknut-afs-disc",
        description="Inspect and mutate Acorn L3 File Server (AFS) disc images",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_info = sub.add_parser("info", help="Print disc and AFS metadata")
    p_info.add_argument("path", type=Path)
    p_info.set_defaults(func=cmd_info)

    p_ls = sub.add_parser("ls", help="List AFS directory entries")
    p_ls.add_argument("path", type=Path)
    p_ls.add_argument("afs_path", nargs="?", default="$")
    p_ls.set_defaults(func=cmd_ls)

    p_cat = sub.add_parser("cat", help="Write an AFS file's bytes to stdout")
    p_cat.add_argument("path", type=Path)
    p_cat.add_argument("afs_path")
    p_cat.set_defaults(func=cmd_cat)

    p_put = sub.add_parser("put", help="Write a local file to an AFS path")
    p_put.add_argument("path", type=Path)
    p_put.add_argument("afs_path")
    p_put.add_argument("local_file")
    p_put.add_argument("--load", type=lambda s: int(s, 0), default=0)
    p_put.add_argument("--exec", dest="exec_", type=lambda s: int(s, 0), default=0)
    p_put.set_defaults(func=cmd_put)

    p_init = sub.add_parser(
        "initialise",
        help="Create a fresh AFS region on an ADFS disc image",
    )
    p_init.add_argument("path", type=Path)
    p_init.add_argument("--disc-name", required=True)
    p_init.add_argument(
        "--cylinders",
        type=int,
        help="AFS region size in cylinders (default: max available)",
    )
    p_init.add_argument(
        "--user",
        action="append",
        help="User spec as NAME or NAME:S (system); repeat for multiple",
    )
    p_init.add_argument(
        "--omit-user",
        action="append",
        help="Suppress a built-in account (Syst, Boot, or Welcome); repeat for multiple",
    )
    p_init.set_defaults(func=cmd_initialise)

    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
