#!/usr/bin/env python3
"""Fail when a package's public ``__all__`` has symbols no docs page documents.

The safety net for our hand-curated Sphinx reference pages. The stock
``sphinx.ext.coverage`` builder measures coverage per *defining* module
and ignores ``__all__``, so it cannot credit our public-path autodoc
(``oaknut.zip.list_archive`` documented while the function lives in
``oaknut.zip.api``) and nags about internal-but-public helpers. This
checker instead compares each package's declared public surface
(``__all__``) against the objects actually documented in a built
manual's ``objects.inv`` inventory: it credits public-path
documentation and only ever complains about symbols a package itself
exports.

Run it against a built manual's inventory, naming the packages that
manual is responsible for documenting::

    python scripts/check_doc_coverage.py --inventory _site/zip/objects.inv oaknut.zip

Exits non-zero, listing the gaps, if any public symbol is undocumented.
"""

from __future__ import annotations

import argparse
import importlib
import posixpath
import sys
from pathlib import Path

from sphinx.util.inventory import InventoryFile


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inventory",
        required=True,
        type=Path,
        help="path to the built manual's objects.inv",
    )
    parser.add_argument(
        "packages",
        nargs="+",
        help="packages whose __all__ must be fully documented in the inventory",
    )
    args = parser.parse_args()

    if not args.inventory.is_file():
        raise SystemExit(
            f"inventory not found: {args.inventory} — build the HTML docs first"
        )

    documented = documented_py_names(args.inventory)

    missing: dict[str, list[str]] = {}
    for package in args.packages:
        gaps = [
            name
            for name in public_names(package)
            if f"{package}.{name}" not in documented
        ]
        if gaps:
            missing[package] = gaps

    if missing:
        print(f"Undocumented public API symbols ({args.inventory}):\n")
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

    print(f"All public API symbols documented for: {', '.join(args.packages)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
