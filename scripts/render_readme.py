#!/usr/bin/env python3
"""Render the workspace's READMEs from their Jinja2 templates.

The root README.md and README-pypi.md are generated from each oaknut-*
sub-package's pyproject.toml:

- README.md is the developer-facing landing page on GitHub. Its template,
  scripts/readme-templates/README.md.j2, also embeds Python example scripts
  from scripts/readme-examples/ that are executed at render time so the
  README always shows runnable code next to its exact output.

- README-pypi.md is the short long-description used by the bare `oaknut`
  namespace placeholder distribution on PyPI. Its template,
  scripts/readme-templates/README-pypi.md.j2, only lists the family
  members with PyPI links.

A package whose README shows code output or command transcripts keeps a
template at packages/<package>/readme/README.md.j2, rendered to
packages/<package>/README.md. Its examples live in
packages/<package>/readme/examples/.

Templates call two functions, each of which executes an example script in
a fresh temporary directory, with ``scripts/`` on ``PYTHONPATH``:

- ``example(name, fixtures=...)`` shows a Python example's source and its
  output.
- ``transcript(name, fixtures=...)`` shows only the output of a recipe that
  prints a ``$ command`` transcript using ``cli_example_helper.show``.

*fixtures* maps file names in the temporary directory to repository-relative
paths copied there first.

Usage:
    python scripts/render_readme.py          # write every README
    python scripts/render_readme.py --check  # verify all are fresh;
                                             # exit 1 if any is stale

The --check mode is what the pre-commit hook runs.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, StrictUndefined

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIRPATH = REPO_ROOT / "scripts"
TEMPLATE_DIRPATH = SCRIPTS_DIRPATH / "readme-templates"
EXAMPLES_DIRPATH = SCRIPTS_DIRPATH / "readme-examples"
PACKAGES_DIRPATH = REPO_ROOT / "packages"

#: Per-package template location, relative to the package directory.
PACKAGE_README_DIRNAME = "readme"
PACKAGE_EXAMPLES_DIRNAME = "examples"

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
    #: The docs/<body>/ Sphinx manual dedicated to this package, if any.
    docs_body: str | None = None


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
        short_name = name.removeprefix("oaknut-")
        import_path = "oaknut." + short_name.replace("-", "_")
        docs_body = short_name if (REPO_ROOT / "docs" / short_name / "conf.py").is_file() else None
        found[name] = PackageMeta(
            name=name, import_path=import_path, description=description, docs_body=docs_body
        )

    ordered = []
    for name in order:
        if name in found:
            ordered.append(found.pop(name))
    for extra_name in sorted(found):
        ordered.append(found[extra_name])
    return ordered


def _run_example(
    examples_dirpath: Path, example_name: str, fixtures: Mapping[str, str] | None
) -> tuple[str, str]:
    """Execute an example script; return its source and its stdout.

    The script runs with the workspace python (so local editable installs
    resolve) in a fresh temporary directory, into which each *fixtures*
    entry — target file name to repository-relative source path — is
    copied first. ``scripts/`` is on ``PYTHONPATH`` so recipes can import
    ``cli_example_helper``. A failing example is an error, so a stale one
    cannot render.
    """
    example_filepath = (examples_dirpath / f"{example_name}.py").resolve()
    if not example_filepath.is_file():
        raise FileNotFoundError(f"example not found: {example_filepath}")

    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(
            [str(SCRIPTS_DIRPATH), *filter(None, [os.environ.get("PYTHONPATH")])]
        ),
        "COLUMNS": "80",
    }
    work_dirpath = Path(tempfile.mkdtemp(prefix="oaknut-readme-"))
    try:
        for target_filename, source_relpath in (fixtures or {}).items():
            shutil.copy2(REPO_ROOT / source_relpath, work_dirpath / target_filename)
        result = subprocess.run(
            [sys.executable, str(example_filepath)],
            capture_output=True,
            text=True,
            check=False,
            cwd=work_dirpath,
            env=env,
        )
    finally:
        shutil.rmtree(work_dirpath, ignore_errors=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"example {example_name!r} failed with exit {result.returncode}:\n"
            f"--- stdout ---\n{result.stdout}"
            f"--- stderr ---\n{result.stderr}"
        )
    return example_filepath.read_text(), result.stdout


def render_example(
    example_name: str,
    fixtures: Mapping[str, str] | None = None,
    *,
    examples_dirpath: Path = EXAMPLES_DIRPATH,
) -> str:
    """Return a Markdown code block showing an example script and its stdout.

    Renders:

        ```python
        <source, with the module docstring stripped>
        ```

        Output:

        ```text
        <stdout>
        ```
    """
    source, stdout = _run_example(examples_dirpath, example_name, fixtures)
    source_for_readme = _strip_module_docstring(source).strip() + "\n"
    output = stdout.rstrip() + "\n"
    return f"```python\n{source_for_readme}```\n\nOutput:\n\n```text\n{output}```"


def render_transcript(
    example_name: str,
    fixtures: Mapping[str, str] | None = None,
    *,
    examples_dirpath: Path = EXAMPLES_DIRPATH,
) -> str:
    """Return a Markdown code block holding a recipe's ``$ command`` transcript."""
    _source, stdout = _run_example(examples_dirpath, example_name, fixtures)
    return f"```\n{stdout.rstrip()}\n```"


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


def _jinja_env(*template_dirpaths: Path) -> Environment:
    return Environment(
        loader=ChoiceLoader(
            [FileSystemLoader(dirpath) for dirpath in (*template_dirpaths, TEMPLATE_DIRPATH)]
        ),
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


def render_package_readme(package_dirpath: Path) -> str:
    """Render a package's README from its readme/ template.

    The template sees ``package`` (its :class:`PackageMeta`) and the
    ``example`` and ``transcript`` functions, and can import the shared
    header and licence macros from ``scripts/readme-templates/package.md.j2``.
    """
    readme_dirpath = package_dirpath / PACKAGE_README_DIRNAME
    examples_dirpath = readme_dirpath / PACKAGE_EXAMPLES_DIRNAME
    template = _jinja_env(readme_dirpath).get_template(README_TEMPLATE_FILENAME)
    package = next(meta for meta in load_packages() if meta.name == package_dirpath.name)
    return template.render(
        package=package,
        example=partial(render_example, examples_dirpath=examples_dirpath),
        transcript=partial(render_transcript, examples_dirpath=examples_dirpath),
    )


@dataclass(frozen=True)
class RenderTarget:
    name: str
    output_filepath: Path
    render: Callable[[], str]


def _package_targets() -> tuple[RenderTarget, ...]:
    """A target for each package that keeps a README template."""
    return tuple(
        RenderTarget(
            str(package_dirpath.relative_to(REPO_ROOT) / "README.md"),
            package_dirpath / "README.md",
            partial(render_package_readme, package_dirpath),
        )
        for package_dirpath in sorted(
            template_filepath.parent.parent
            for template_filepath in PACKAGES_DIRPATH.glob(
                f"oaknut-*/{PACKAGE_README_DIRNAME}/{README_TEMPLATE_FILENAME}"
            )
        )
    )


TARGETS: tuple[RenderTarget, ...] = (
    RenderTarget("README.md", README_OUTPUT_FILEPATH, render_readme),
    RenderTarget("README-pypi.md", PYPI_README_OUTPUT_FILEPATH, render_pypi_readme),
    *_package_targets(),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the generated READMEs are up to date without writing. "
        "Exits 1 if any is stale.",
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
