"""Sphinx configuration for the oaknut disc manual.

Generic settings — theme, the common extension set, autodoc /
intersphinx / napoleon defaults, and the shared static assets — come
from ``docs/_shared/conf_base.py`` via the star-import below. This file
keeps only what is specific to the disc manual: its title and the
CLI-documentation directives (``oaknut-command`` and ``cli-example``).
"""

import re
import subprocess
import sys
from pathlib import Path

from docutils import nodes
from docutils.parsers.rst import Directive

# Shared base config: extensions, theme, html_static_path, and the
# autodoc / intersphinx / napoleon defaults common to every body.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from conf_base import *  # noqa: E402, F403

# Local extensions under docs/disc/_ext/.
sys.path.insert(0, str(Path(__file__).resolve().parent / "_ext"))

project = "oaknut"
html_title = "oaknut"
html_logo = "_static/oaknut-disc-logo.png"

# Disc-specific extensions on top of the shared set: sphinx_click for
# any residual `.. click::` usage, and oaknut_command for the semantic
# `.. oaknut-command::` directive.
extensions = [*extensions, "sphinx_click", "oaknut_command"]  # noqa: F405


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

        # Some recipes legitimately emit tab characters — `ls -C` is
        # the prototype, where BSD ls aligns columns with tabs. Expand
        # them here so the rendered literal block aligns identically
        # whatever tab-size the HTML/CSS layer picks. 8-stop matches
        # the assumption every Unix tool that emits tabs makes.
        display_text = display_text.expandtabs(8)

        block = nodes.literal_block(display_text, display_text)
        block["language"] = "disc-session"
        return [block]


# Pygments' BashSessionLexer only treats ``>`` continuation lines as
# part of a command when the previous line ended with a backslash.
# Our cli-example transcripts use bare ``>`` continuations for shell
# constructs like ``for`` loops, where the multi-line input is
# implicit. Enabling ``_bare_continuation`` makes the lexer treat any
# ``>`` line after a ``$`` prompt as still belonging to the command,
# so syntax highlighting carries across the whole multi-line input.
def _register_disc_session_lexer(app):
    from pygments.lexers.shell import BashSessionLexer

    class DiscSessionLexer(BashSessionLexer):
        name = "Disc Session"
        aliases = ["disc-session"]
        _bare_continuation = True

    app.add_lexer("disc-session", DiscSessionLexer)


def setup(app):
    app.add_directive("cli-example", CliExampleDirective)
    _register_disc_session_lexer(app)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
