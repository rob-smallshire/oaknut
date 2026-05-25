#!/usr/bin/env python3
"""Documentation coverage checks for the oaknut manuals.

Two complementary gaps this guards, exposed as subcommands so both run
the same way (parse → report gaps → exit non-zero):

``api``
    Fail when a package's public ``__all__`` has symbols that no
    reference page documents. The stock ``sphinx.ext.coverage`` builder
    measures coverage per *defining* module and ignores ``__all__``, so
    it cannot credit our public-path autodoc (``oaknut.zip.list_archive``
    documented while the function lives in ``oaknut.zip.api``) and nags
    about internal-but-public helpers. This checker compares each
    package's declared public surface (``__all__``) against the objects
    in a built manual's ``objects.inv`` inventory: it credits public-path
    documentation and only complains about symbols a package exports. A
    symbol counts as documented when its public name (``oaknut.dfs.DFS``)
    is in the inventory, or when the *same object* is documented under
    any other name — so a re-exported symbol is credited by its
    canonical entry. Needs the HTML build first (it reads ``objects.inv``).

``commands``
    Fail when a ``disc`` CLI subcommand is missing from the command
    reference (``docs/disc/cli/commands/index.rst``), when the reference
    documents a command that no longer exists, or when a documented
    command lacks a ``cli-example`` whose recipe script exists under
    ``scripts/cli-examples/``. Needs only the source tree — no build.

Run via :mod:`build_docs` (``scripts/build_docs.sh coverage``), or
directly::

    python scripts/check_doc_coverage.py commands
    python scripts/check_doc_coverage.py api --inventory _site/zip/objects.inv oaknut.zip
"""

from __future__ import annotations

import argparse
import importlib
import posixpath
import re
import sys
from pathlib import Path

from sphinx.util.inventory import InventoryFile

_REPO_ROOT = Path(__file__).resolve().parent.parent
_COMMAND_REFERENCE_FILEPATH = _REPO_ROOT / "docs" / "disc" / "cli" / "commands" / "index.rst"
_EXAMPLES_DIRPATH = _REPO_ROOT / "scripts" / "cli-examples"


# ---------------------------------------------------------------------------
# api — public __all__ vs the built objects.inv inventory
# ---------------------------------------------------------------------------


def documented_py_names(inventory_filepath: Path) -> set[str]:
    """Return every fully-qualified Python object name in *inventory_filepath*."""
    with inventory_filepath.open("rb") as stream:
        inventory = InventoryFile.load(stream, "", posixpath.join)
    names: set[str] = set()
    for object_type, entries in inventory.items():
        if object_type.startswith("py:"):
            names.update(entries)
    return names


def public_names(package: str) -> list[str]:
    """Return *package*'s declared public API (its ``__all__``)."""
    module = importlib.import_module(package)
    exported = getattr(module, "__all__", None)
    if exported is None:
        raise SystemExit(
            f"{package} does not define __all__, so its public API is "
            f"undefined; declare __all__ before gating its docs coverage."
        )
    return list(exported)


def resolve(dotted_name: str) -> object | None:
    """Resolve a documented dotted name to the live object, or None.

    Imports the longest importable module prefix, then walks the
    remaining components as attributes.
    """
    parts = dotted_name.split(".")
    for split in range(len(parts), 0, -1):
        try:
            obj: object = importlib.import_module(".".join(parts[:split]))
        except ModuleNotFoundError:
            continue
        try:
            for attribute in parts[split:]:
                obj = getattr(obj, attribute)
        except AttributeError:
            return None
        return obj
    return None


def check_api(inventory_filepath: Path, packages: list[str]) -> int:
    """Check that every package's ``__all__`` is documented in the inventory."""
    if not inventory_filepath.is_file():
        raise SystemExit(
            f"inventory not found: {inventory_filepath} — build the HTML docs first"
        )

    documented = documented_py_names(inventory_filepath)

    # Index documented names by their final component, so a re-exported
    # symbol can be matched against the canonical entry that documents
    # the same object under a different qualifier.
    documented_by_leaf: dict[str, set[str]] = {}
    for name in documented:
        documented_by_leaf.setdefault(name.rsplit(".", 1)[-1], set()).add(name)

    def is_documented(package: str, name: str) -> bool:
        if f"{package}.{name}" in documented:
            return True
        obj = getattr(importlib.import_module(package), name)
        return any(
            resolve(candidate) is obj
            for candidate in documented_by_leaf.get(name, ())
        )

    missing: dict[str, list[str]] = {}
    for package in packages:
        gaps = [name for name in public_names(package) if not is_documented(package, name)]
        if gaps:
            missing[package] = gaps

    if missing:
        print(f"Undocumented public API symbols ({inventory_filepath}):\n")
        for package, gaps in missing.items():
            print(f"  {package}:")
            for name in gaps:
                print(f"    - {package}.{name}")
        total = sum(len(gaps) for gaps in missing.values())
        print(
            f"\n{total} undocumented public symbol(s). Document them on a "
            f"reference page, or drop them from __all__."
        )
        return 1

    print(f"All public API symbols documented for: {', '.join(packages)}")
    return 0


# ---------------------------------------------------------------------------
# commands — disc CLI subcommands vs the command reference
# ---------------------------------------------------------------------------

_OAKNUT_COMMAND_RE = re.compile(
    r"^\.\. oaknut-command:: oaknut\.disc\.cli:(\S+)\s*$", re.MULTILINE
)
_CLI_EXAMPLE_RE = re.compile(r"cli-example:: (\S+)")


def cli_command_names() -> set[str]:
    """Primary ``disc`` subcommands (excluding Acorn ``*`` star-aliases)."""
    from oaknut.disc.cli import cli

    return {name for name in cli.commands if not name.startswith("*")}


def documented_commands(reference_filepath: Path) -> dict[str, list[str]]:
    """Map each documented command to the cli-example scripts in its block.

    A command's block runs from its ``.. oaknut-command::`` line up to
    the next one (or end of file) — where its ``:prog:`` line, prose,
    and ``.. cli-example::`` directives live.
    """
    text = reference_filepath.read_text()
    matches = list(_OAKNUT_COMMAND_RE.finditer(text))
    documented: dict[str, list[str]] = {}
    for index, match in enumerate(matches):
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        documented[match.group(1)] = _CLI_EXAMPLE_RE.findall(text[block_start:block_end])
    return documented


def check_commands(reference_filepath: Path, examples_dirpath: Path) -> int:
    """Check command/example coverage of the disc CLI command reference."""
    if not reference_filepath.is_file():
        raise SystemExit(f"command reference not found: {reference_filepath}")

    commands = cli_command_names()
    documented = documented_commands(reference_filepath)

    problems: list[str] = []

    undocumented = sorted(commands - set(documented))
    if undocumented:
        problems.append(
            "commands with no .. oaknut-command:: entry: " + ", ".join(undocumented)
        )

    stale = sorted(set(documented) - commands)
    if stale:
        problems.append(
            "documented commands that no longer exist on the CLI: " + ", ".join(stale)
        )

    without_example = sorted(name for name, examples in documented.items() if not examples)
    if without_example:
        problems.append(
            "documented commands with no .. cli-example:: directive: "
            + ", ".join(without_example)
        )

    missing_scripts = sorted(
        f"{name} -> {example}.py"
        for name, examples in documented.items()
        for example in examples
        if not (examples_dirpath / f"{example}.py").is_file()
    )
    if missing_scripts:
        problems.append(
            "cli-example scripts referenced but absent: " + ", ".join(missing_scripts)
        )

    if problems:
        print(f"Command reference coverage gaps ({reference_filepath}):\n")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\nEvery disc subcommand needs an .. oaknut-command:: entry with a "
            "cli-example whose recipe exists; remove entries for deleted commands."
        )
        return 1

    print(f"All {len(commands)} disc CLI commands documented with an example.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    api = subparsers.add_parser("api", help="check public __all__ against a built inventory")
    api.add_argument(
        "--inventory", required=True, type=Path, help="path to the built manual's objects.inv"
    )
    api.add_argument(
        "packages",
        nargs="+",
        help="packages whose __all__ must be fully documented in the inventory",
    )

    commands = subparsers.add_parser(
        "commands", help="check disc CLI commands against the command reference"
    )
    commands.add_argument(
        "--reference",
        type=Path,
        default=_COMMAND_REFERENCE_FILEPATH,
        help="path to the command reference index.rst",
    )
    commands.add_argument(
        "--examples-dir",
        type=Path,
        default=_EXAMPLES_DIRPATH,
        help="directory holding the cli-example recipe scripts",
    )

    args = parser.parse_args()

    if args.command == "api":
        return check_api(args.inventory, args.packages)
    if args.command == "commands":
        return check_commands(args.reference, args.examples_dir)
    raise AssertionError(f"unhandled subcommand {args.command!r}")  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
