"""Sphinx configuration for the oaknut basic manual.

Generic settings — theme, the common extension set, autodoc /
intersphinx / napoleon defaults, and the shared static assets — come
from ``docs/_shared/conf_base.py`` via the star-import below. This file
keeps only what is specific to the basic manual: its title and the
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

# Local extensions under docs/basic/_ext/.
sys.path.insert(0, str(Path(__file__).resolve().parent / "_ext"))

project = "oaknut-basic"
html_title = "oaknut-basic"
html_logo = "_static/oaknut-basic-logo.png"

# The semantic `.. oaknut-command::` directive, shared with the disc
# manual, renders one Click command as definition lists.
extensions = [*extensions, "oaknut_command"]  # noqa: F405


# ---------------------------------------------------------------------------
# `.. cli-example:: <name>` — runnable CLI example recipes.
#
# A recipe is a Python script at scripts/cli-examples/<name>.py that uses
# the helpers in scripts/cli_example_helper.py to invoke a CLI and print a
# `$ command` / output transcript. At build time the directive executes the
# script and embeds its stdout as a console-styled literal block, so the
# manual's example output cannot drift from the actual binary's behaviour (a
# stale or broken example fails sphinx-build -W).
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CLI_EXAMPLES_DIRPATH = _REPO_ROOT / "scripts" / "cli-examples"

# Sentinel format kept in sync with scripts/cli_example_helper.section().
_SECTION_MARKER_RE = re.compile(r"\x1f@@OAKNUT_SECTION@@(\S+)")

# Recipe outputs are cached at module scope so a page with several
# `.. cli-example:: NAME :section: ...` directives pointing at the same
# recipe runs that recipe only once per docs build.
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
    """Parse `raw` into a {section_name: body} dict via the marker lines."""
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

    A bare ``.. cli-example:: name`` emits the whole captured stdout (with
    any section markers stripped). Passing ``:section: foo`` emits just the
    body of the ``foo`` section. The recipe runs at most once per docs
    build, regardless of how many directives target it.
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
        block["language"] = "disc-session"
        return [block]


# Pygments' BashSessionLexer only treats ``>`` continuation lines as part of
# a command when the previous line ended with a backslash. Our transcripts
# use bare ``>`` continuations for shell constructs, so enable
# ``_bare_continuation`` to carry highlighting across the whole input.
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
