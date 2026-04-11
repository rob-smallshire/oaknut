#!/usr/bin/env python3
"""Render README.md from docs/README.md.j2.

The template references Python example scripts in docs/readme_examples/.
Each example is executed in a subprocess and its source + stdout are
interleaved into a single Markdown code block, so the README always
shows runnable code next to the exact output the reader will see if
they run it themselves.

Usage:
    python scripts/render_readme.py          # write README.md
    python scripts/render_readme.py --check  # verify README.md is fresh;
                                             # exit 1 if it would change

The --check mode is what the pre-commit hook runs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIRPATH = REPO_ROOT / "docs"
TEMPLATE_FILENAME = "README.md.j2"
EXAMPLES_DIRPATH = REPO_ROOT / "docs" / "readme_examples"
PACKAGES_DIRPATH = REPO_ROOT / "packages"
OUTPUT_FILEPATH = REPO_ROOT / "README.md"

PACKAGE_ORDER = (
    "oaknut-file",
    "oaknut-discimage",
    "oaknut-basic",
    "oaknut-dfs",
    "oaknut-adfs",
    "oaknut-zip",
)


@dataclass(frozen=True)
class PackageMeta:
    name: str
    import_path: str
    description: str


def load_packages() -> list[PackageMeta]:
    """Collect metadata from every packages/oaknut-*/pyproject.toml."""
    found: dict[str, PackageMeta] = {}
    for pyproject_filepath in sorted(PACKAGES_DIRPATH.glob("oaknut-*/pyproject.toml")):
        with pyproject_filepath.open("rb") as f:
            data = tomllib.load(f)
        project = data["project"]
        name = project["name"]
        description = project["description"].rstrip(".")
        import_path = "oaknut." + name.removeprefix("oaknut-").replace("-", "_")
        found[name] = PackageMeta(name=name, import_path=import_path, description=description)

    ordered = []
    for name in PACKAGE_ORDER:
        if name in found:
            ordered.append(found.pop(name))
    for extra_name in sorted(found):
        ordered.append(found[extra_name])
    return ordered


def render_example(example_name: str) -> str:
    """Return a Markdown code block showing an example script and its stdout.

    The example is a standalone .py file under docs/readme_examples/. We
    execute it with the workspace python (so local editable installs
    resolve), capture stdout, and render:

        ```python
        <source, with the module docstring stripped>
        ```

        ```text
        <stdout>
        ```
    """
    example_filepath = EXAMPLES_DIRPATH / f"{example_name}.py"
    if not example_filepath.is_file():
        raise FileNotFoundError(f"example not found: {example_filepath}")

    source = example_filepath.read_text()
    source_for_readme = _strip_module_docstring(source).strip() + "\n"

    result = subprocess.run(
        [sys.executable, str(example_filepath)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"example {example_name!r} failed with exit {result.returncode}:\n"
            f"--- stdout ---\n{result.stdout}"
            f"--- stderr ---\n{result.stderr}"
        )

    output = result.stdout.rstrip() + "\n"

    return (
        f"```python\n{source_for_readme}```\n\n"
        f"Output:\n\n"
        f"```text\n{output}```"
    )


def _strip_module_docstring(source: str) -> str:
    """Remove the leading module-level triple-quoted docstring, if any.

    Example scripts have a docstring explaining *why* the example exists,
    which belongs in the source but is redundant next to the surrounding
    README prose. Strip it so the code block is tight.
    """
    stripped = source.lstrip()
    if not stripped.startswith('"""'):
        return source
    closing = stripped.find('"""', 3)
    if closing == -1:
        return source
    after_docstring = stripped[closing + 3 :]
    leading_ws = source[: len(source) - len(stripped)]
    return leading_ws + after_docstring.lstrip("\n")


def render_readme() -> str:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIRPATH),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    template = env.get_template(TEMPLATE_FILENAME)
    return template.render(
        packages=load_packages(),
        example=render_example,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify README.md is up to date without writing. Exits 1 if stale.",
    )
    args = parser.parse_args()

    rendered = render_readme()

    if args.check:
        current = OUTPUT_FILEPATH.read_text() if OUTPUT_FILEPATH.exists() else ""
        if current != rendered:
            print(
                "README.md is out of date. Regenerate it with:\n"
                "    uv run python scripts/render_readme.py",
                file=sys.stderr,
            )
            return 1
        return 0

    OUTPUT_FILEPATH.write_text(rendered)
    print(f"wrote {OUTPUT_FILEPATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
