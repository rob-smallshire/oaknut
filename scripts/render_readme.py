#!/usr/bin/env python3
"""Render README.md and README-pypi.md from their Jinja2 templates.

Both READMEs are generated from each oaknut-* sub-package's pyproject.toml:

- README.md is the developer-facing landing page on GitHub. Its template,
  scripts/readme-templates/README.md.j2, also embeds Python example scripts
  from scripts/readme-examples/ that are executed at render time so the
  README always shows runnable code next to its exact output.

- README-pypi.md is the short long-description used by the bare `oaknut`
  namespace placeholder distribution on PyPI. Its template,
  scripts/readme-templates/README-pypi.md.j2, only lists the family
  members with PyPI links.

Usage:
    python scripts/render_readme.py          # write both READMEs
    python scripts/render_readme.py --check  # verify both are fresh;
                                             # exit 1 if either is stale

The --check mode is what the pre-commit hook runs.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIRPATH = REPO_ROOT / "scripts" / "readme-templates"
EXAMPLES_DIRPATH = REPO_ROOT / "scripts" / "readme-examples"
PACKAGES_DIRPATH = REPO_ROOT / "packages"

README_TEMPLATE_FILENAME = "README.md.j2"
README_OUTPUT_FILEPATH = REPO_ROOT / "README.md"

PYPI_README_TEMPLATE_FILENAME = "README-pypi.md.j2"
PYPI_README_OUTPUT_FILEPATH = REPO_ROOT / "README-pypi.md"

# Preferred ordering for the GitHub README's package table — packages
# listed here come first, in this order, with any unlisted ones
# appended alphabetically. The PyPI placeholder renders with order=()
# for pure alphabetical.
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


def load_packages(order: tuple[str, ...] = PACKAGE_ORDER) -> list[PackageMeta]:
    """Collect metadata from every packages/oaknut-*/pyproject.toml.

    Packages named in ``order`` come first, in that order. Any remaining
    packages are appended alphabetically. Pass ``order=()`` for pure
    alphabetical ordering — that is what the PyPI placeholder template
    uses, since it has no opinion about layer/value ordering.
    """
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
    for name in order:
        if name in found:
            ordered.append(found.pop(name))
    for extra_name in sorted(found):
        ordered.append(found[extra_name])
    return ordered


def render_example(example_name: str) -> str:
    """Return a Markdown code block showing an example script and its stdout.

    The example is a standalone .py file under scripts/readme-examples/. We
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

    return f"```python\n{source_for_readme}```\n\nOutput:\n\n```text\n{output}```"


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


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIRPATH),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render_readme() -> str:
    template = _jinja_env().get_template(README_TEMPLATE_FILENAME)
    return template.render(
        packages=load_packages(),
        example=render_example,
    )


def render_pypi_readme() -> str:
    template = _jinja_env().get_template(PYPI_README_TEMPLATE_FILENAME)
    return template.render(packages=load_packages(order=()))


@dataclass(frozen=True)
class RenderTarget:
    name: str
    output_filepath: Path
    render: Callable[[], str]


TARGETS: tuple[RenderTarget, ...] = (
    RenderTarget("README.md", README_OUTPUT_FILEPATH, render_readme),
    RenderTarget("README-pypi.md", PYPI_README_OUTPUT_FILEPATH, render_pypi_readme),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the generated READMEs are up to date without writing. "
        "Exits 1 if either is stale.",
    )
    args = parser.parse_args()

    stale: list[str] = []
    for target in TARGETS:
        rendered = target.render()
        if args.check:
            current = target.output_filepath.read_text() if target.output_filepath.exists() else ""
            if current != rendered:
                stale.append(target.name)
            continue
        target.output_filepath.write_text(rendered)
        print(f"wrote {target.output_filepath.relative_to(REPO_ROOT)}")

    if args.check and stale:
        print(
            f"{', '.join(stale)} out of date. Regenerate with:\n"
            "    uv run python scripts/render_readme.py",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
