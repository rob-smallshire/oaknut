"""Build-time helper for CLI example recipes.

Recipes under ``scripts/cli-examples/`` use the three helpers in
this module to invoke the ``disc`` CLI and produce the
``$ command``/output transcript that the ``cli-example`` Sphinx
directive embeds in the manual.

Two kinds of invocation:

- :func:`show` — what the reader is meant to learn. Prints ``$ cmd``
  on its own line, then the command's combined stdout/stderr. For
  ``disc`` subcommands that produce tabular reports (``ls``, ``tree``,
  ``stat``, ``find``, ``afs plan``, ``afs users``, …), ``--as display``
  is appended to the *executed* command so the reader sees the boxed
  terminal rendering rather than the pipe-style TSV that ``asyoulikeit``
  would otherwise auto-pick when stdout is captured. The ``--as
  display`` flag is stripped from the printed ``$ command`` line so the
  reader copies exactly what they should type. A non-zero exit fails the
  build, so a stale or broken example cannot slip through.

- :func:`show_error` — the same transcript, but for a command that is
  *meant* to fail (demonstrating an error message). Here a zero exit is
  the build failure: an error example that stops erroring is itself
  drift.

- :func:`silent` — recipe scaffolding the reader is meant to ignore.
  Builds fixtures, populates discs, etc. The command runs but its
  invocation and output are dropped. ``check=True``: a failed setup
  step is a build error.

Recipes typically run inside :func:`in_tmp_dir` so each invocation
gets a fresh, disposable working directory. :func:`copy_from_corpus`
pulls a shipped image from ``tests/data/images/cookbook/`` into the
current directory for recipes that need realistic data.
"""

from __future__ import annotations

import contextlib
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

__all__ = [
    "show",
    "show_error",
    "silent",
    "section",
    "in_tmp_dir",
    "copy_from_corpus",
]


#: Sentinel emitted by :func:`section` and recognised by the
#: ``cli-example`` Sphinx directive. ASCII Unit Separator + an
#: unambiguous tag — neither component appears in normal command
#: output, so the marker round-trips cleanly through stdout capture
#: without colliding with anything a recipe might legitimately print.
_SECTION_MARKER_PREFIX = "\x1f@@OAKNUT_SECTION@@"


def section(name: str) -> None:
    """Mark the start of a named section in the captured transcript.

    The ``cli-example`` directive in ``docs/disc/conf.py``
    recognises these markers and can extract just the named section
    into a page block via ``:section: <name>``. This lets a long,
    stateful recipe be interleaved with explanatory prose without
    being rebuilt from scratch for each step — the recipe runs once
    per docs build and its output is sliced on demand.

    Sections are sequential: each call closes the previous section
    and opens the new one. Content before the first call is
    accessible only through the no-``:section:`` default (full
    transcript with markers stripped).
    """
    print(f"{_SECTION_MARKER_PREFIX}{name}")


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "tests" / "data" / "images" / "cookbook"


# disc subcommands that wear the @report_output decorator and
# therefore benefit from `--as display` at capture time. Subcommands
# not on this list (`cat`, `type`, `freemap`, `put`, `get`, `cp`,
# `mv`, `rm`, `mkdir`, `chmod`, `lock`, `unlock`, `set-*`,
# `validate`, `create`, `compact`, `dfs expand`, `afs init`,
# `afs merge`, etc.) reject `--as` — passing it would make the recipe
# fail. Grouped subcommands are spelled with the space (`afs plan`).
_REPORT_SUBCOMMANDS = frozenset(
    {
        "ls",
        "tree",
        "stat",
        "find",
        "title",
        "opt",
        "get-load",
        "get-exec",
        "afs plan",
        "afs users",
        "list-reports",
        "describe-report",
        "list-report-formats",
        "describe-report-format",
        "identify",
        "list-formats",
        "describe-format",
    }
)


def _needs_display_flag(command: str) -> bool:
    """Return True if we should append ``--as display`` to *command*.

    True only when the command is a ``disc`` invocation, its
    subcommand emits report output, and the caller has not already
    set ``--as`` themselves.
    """
    if "--as" in command:
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 2 or tokens[0] != "disc":
        return False
    # A top-level subcommand (`ls`) or a grouped one (`afs plan`).
    if tokens[1] in _REPORT_SUBCOMMANDS:
        return True
    return len(tokens) >= 3 and f"{tokens[1]} {tokens[2]}" in _REPORT_SUBCOMMANDS


def _capture_env() -> dict[str, str]:
    """Subprocess env: fix terminal width so boxed output is reproducible."""
    return {**os.environ, "COLUMNS": "80"}


def show(command: str) -> None:
    """Run *command* and write ``$ command``/output to stdout.

    Composed example recipes call ``show`` once per command they want
    the reader to see. Raises :class:`SystemExit` (non-zero) if the
    command fails, so a stale or broken example fails the docs build.

    The displayed ``$ command`` line is the command as the recipe
    wrote it — no auto-appended ``--as display`` leaks through to the
    reader. The executed command may differ; see module docstring.

    Multi-line commands (shell ``for`` loops, ``if``/``then``/``fi``
    blocks, anything with embedded newlines) are rendered with a
    ``> `` continuation prompt on subsequent lines, the same way a
    real interactive shell echoes them.
    """
    lines = command.splitlines() or [""]
    print(f"$ {lines[0]}")
    for cont in lines[1:]:
        print(f"> {cont}")

    run_command = command
    if _needs_display_flag(command):
        run_command = f"{command} --as display"

    result = subprocess.run(
        run_command,
        shell=True,
        capture_output=True,
        text=True,
        env=_capture_env(),
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        # Inline stderr after stdout — keeps order roughly readable
        # for commands that emit warnings or progress to stderr.
        sys.stdout.write(result.stderr)
    if result.returncode != 0:
        sys.stderr.write(
            f"\nrecipe step failed: {command}\n"
            f"  executed: {run_command}\n"
            f"  exit code: {result.returncode}\n"
        )
        sys.exit(result.returncode)


def show_error(command: str, *, returncode: int | None = None) -> None:
    """Run a command expected to *fail* and show its ``$ command``/output.

    For demonstrating error messages — the inverse of :func:`show`. The
    transcript is captured identically (``$ command`` then combined
    stdout/stderr), but the success condition is reversed: the command
    must exit non-zero, so an error example that stops erroring fails the
    docs build. Pass *returncode* to require a specific exit code rather
    than just "any failure". No ``--as display`` is appended — errors
    print as plain text.
    """
    lines = command.splitlines() or [""]
    print(f"$ {lines[0]}")
    for cont in lines[1:]:
        print(f"> {cont}")

    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        env=_capture_env(),
    )
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stdout.write(result.stderr)

    failed_as_expected = (
        result.returncode != 0 if returncode is None else result.returncode == returncode
    )
    if not failed_as_expected:
        expected = "non-zero" if returncode is None else str(returncode)
        sys.stderr.write(
            f"\nerror example did not fail as expected: {command}\n"
            f"  expected exit: {expected}\n"
            f"  actual exit: {result.returncode}\n"
        )
        sys.exit(1)


def silent(command: str) -> None:
    """Run *command* without showing its invocation or output.

    For fixture / setup steps the reader should not see. Raises
    :class:`subprocess.CalledProcessError` on non-zero exit so a
    broken setup step fails the docs build loudly.
    """
    subprocess.run(
        command,
        shell=True,
        check=True,
        capture_output=True,
        env=_capture_env(),
    )


@contextlib.contextmanager
def in_tmp_dir() -> Iterator[Path]:
    """Run the body in a fresh temporary directory.

    Yields the temp directory path so the recipe can reference it if
    needed. The directory is removed unconditionally on exit, even
    if the body raised.
    """
    original = Path.cwd()
    tmp = Path(tempfile.mkdtemp(prefix="oaknut-cli-example-"))
    try:
        os.chdir(tmp)
        yield tmp
    finally:
        os.chdir(original)
        shutil.rmtree(tmp, ignore_errors=True)


def copy_from_corpus(name: str, target_name: str | None = None) -> Path:
    """Copy a shipped corpus image into the current directory.

    The corpus lives at ``tests/data/images/cookbook/`` and is
    reserved for images that are genuinely hard to synthesise — a
    populated Level 3 File Server disc, a dual-partition ADFS+AFS
    image, etc. Most recipes should build their own inputs via
    ``disc create`` + ``disc put``.

    *name* is the file name within the corpus directory.
    *target_name* defaults to the same name. Returns the path of the
    copy (relative to the current directory).

    Raises :class:`FileNotFoundError` if the named image is not in
    the corpus.
    """
    source = CORPUS_ROOT / name
    if not source.is_file():
        raise FileNotFoundError(f"corpus image not found: {source}")
    target = Path(target_name or name)
    shutil.copy2(source, target)
    return target
