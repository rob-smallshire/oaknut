"""Sphinx configuration for oaknut documentation."""

import subprocess
import sys
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive

project = "oaknut"
author = "Robert Smallshire"
copyright = "2024-2026, Robert Smallshire"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx_click",
    "sphinx_copybutton",
    "sphinx_design",
]

# Theme
html_theme = "sphinx_clarity_theme"
html_title = "oaknut"

# Custom static assets. _static/platform-tabs.js auto-selects the
# host-platform tab in sphinx-design tab-sets that use the :sync: IDs
# `bash` / `zsh` / `powershell` (see _static/platform-tabs.js for the
# detection logic and conventions).
html_static_path = ["_static"]
html_js_files = ["platform-tabs.js"]

# Autodoc
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Source
exclude_patterns = ["_build"]

# Suppress warnings from star-aliases (*CAT etc.) in Click docstrings
# that sphinx-click renders — the * is misinterpreted as RST emphasis.
suppress_warnings = ["docutils"]


# ---------------------------------------------------------------------------
# `.. cli-example:: <name>` — runnable CLI example recipes.
#
# A recipe is a Python script at scripts/cli-examples/<name>.py that uses
# the helpers in scripts/cli_example_helper.py to invoke `disc` and print
# a `$ command` / output transcript. At build time the directive executes
# the script and embeds its stdout as a console-styled literal block, so
# the manual's example output cannot drift from the actual binary's
# behaviour (a stale or broken example fails sphinx-build -W).
#
# Conventions inside a recipe:
#   - `show("disc stat hello.ssd")` — prints the command and its output;
#     auto-appends `--as display` for report subcommands so the captured
#     output matches what a user sees on their interactive terminal.
#   - `silent("…")` — runs a setup step the reader is not meant to see.
#   - `with in_tmp_dir():` — sandbox the recipe in a fresh temp directory.
# ---------------------------------------------------------------------------

import re

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CLI_EXAMPLES_DIRPATH = _REPO_ROOT / "scripts" / "cli-examples"

# Sentinel format kept in sync with scripts/cli_example_helper.section().
# The leading \x1f (ASCII Unit Separator) keeps the marker out of the
# way of any legitimate command output.
_SECTION_MARKER_RE = re.compile(r"\x1f@@OAKNUT_SECTION@@(\S+)")

# Recipe outputs are cached at module scope so a page with several
# `.. cli-example:: NAME :section: ...` directives pointing at the
# same recipe runs that recipe only once per docs build. The cache is
# fresh on every `sphinx-build` invocation (the module is reimported).
_RECIPE_CACHE: dict[Path, str] = {}


def _run_recipe(script_filepath: Path) -> str:
    cached = _RECIPE_CACHE.get(script_filepath)
    if cached is not None:
        return cached
    result = subprocess.run(
        [sys.executable, str(script_filepath)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"recipe failed: {script_filepath.name} (exit {result.returncode})\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    _RECIPE_CACHE[script_filepath] = result.stdout
    return result.stdout


def _split_sections(raw: str) -> dict[str, str]:
    """Parse `raw` into a {section_name: body} dict via the marker lines.

    Content before the first marker is discarded — recipe authors who
    want a head section should call ``section()`` first thing.
    """
    sections: dict[str, str] = {}
    current_name: str | None = None
    current_buf: list[str] = []
    for line in raw.splitlines(keepends=True):
        match = _SECTION_MARKER_RE.search(line)
        if match is not None:
            if current_name is not None:
                sections[current_name] = "".join(current_buf)
            current_name = match.group(1)
            current_buf = []
        else:
            if current_name is not None:
                current_buf.append(line)
    if current_name is not None:
        sections[current_name] = "".join(current_buf)
    return sections


def _strip_section_markers(raw: str) -> str:
    """Drop the marker lines, leaving the rest of the transcript intact."""
    return "".join(
        line for line in raw.splitlines(keepends=True) if _SECTION_MARKER_RE.search(line) is None
    )


class CliExampleDirective(Directive):
    """Run a recipe at scripts/cli-examples/<name>.py and embed its transcript.

    A bare ``.. cli-example:: name`` emits the whole captured stdout
    (with any section markers stripped). Passing ``:section: foo``
    emits just the body of the ``foo`` section — see
    :func:`scripts.cli_example_helper.section`. The recipe runs at
    most once per docs build, regardless of how many directives
    target it.
    """

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False
    option_spec = {"section": str}

    def run(self) -> list[nodes.Node]:
        name = self.arguments[0]
        script_filepath = _CLI_EXAMPLES_DIRPATH / f"{name}.py"
        if not script_filepath.is_file():
            return [
                self.state.document.reporter.error(
                    f"cli-example recipe not found: {script_filepath}",
                    line=self.lineno,
                )
            ]

        try:
            raw_output = _run_recipe(script_filepath)
        except RuntimeError as exc:
            return [self.state.document.reporter.error(str(exc), line=self.lineno)]

        section_name = self.options.get("section")
        if section_name is None:
            display_text = _strip_section_markers(raw_output)
        else:
            sections = _split_sections(raw_output)
            if section_name not in sections:
                available = ", ".join(sorted(sections)) or "(none)"
                return [
                    self.state.document.reporter.error(
                        f"cli-example recipe {name!r} has no section "
                        f"{section_name!r}; available: {available}",
                        line=self.lineno,
                    )
                ]
            display_text = sections[section_name]

        block = nodes.literal_block(display_text, display_text)
        block["language"] = "console"
        return [block]


def setup(app):
    app.add_directive("cli-example", CliExampleDirective)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
