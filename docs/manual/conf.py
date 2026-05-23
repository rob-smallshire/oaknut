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

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CLI_EXAMPLES_DIRPATH = _REPO_ROOT / "scripts" / "cli-examples"


class CliExampleDirective(Directive):
    """Run a recipe at scripts/cli-examples/<name>.py and embed its transcript."""

    has_content = False
    required_arguments = 1
    final_argument_whitespace = False

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

        result = subprocess.run(
            [sys.executable, str(script_filepath)],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return [
                self.state.document.reporter.error(
                    f"cli-example recipe failed: {name} (exit {result.returncode})\n"
                    f"--- stdout ---\n{result.stdout}\n"
                    f"--- stderr ---\n{result.stderr}",
                    line=self.lineno,
                )
            ]

        block = nodes.literal_block(result.stdout, result.stdout)
        block["language"] = "console"
        return [block]


def setup(app):
    app.add_directive("cli-example", CliExampleDirective)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
