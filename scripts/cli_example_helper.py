"""Build-time helper for CLI example recipes.

Recipes under ``scripts/cli-examples/`` use the three helpers in
this module to invoke the ``disc`` CLI and produce the
``$ command``/output transcript that the ``cli-example`` Sphinx
directive embeds in the manual.

Two kinds of invocation:

- :func:`show` — what the reader is meant to learn. Prints ``$ cmd``
  on its own line, then the command's combined stdout/stderr. For
  ``disc`` subcommands that produce tabular reports (``ls``,
  ``tree``, ``stat``, ``cat``, ``type``, ``find``, ``freemap``,
  ``afs-plan``, ``afs-users``), ``--as display`` is appended to the
  *executed* command so the reader sees the boxed terminal rendering
  rather than the pipe-style TSV that ``asyoulikeit`` would otherwise
  auto-pick when stdout is captured. The ``--as display`` flag is
  stripped from the printed ``$ command`` line so the reader copies
  exactly what they should type.

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
    "silent",
    "in_tmp_dir",
    "copy_from_corpus",
]


REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_ROOT = REPO_ROOT / "tests" / "data" / "images" / "cookbook"


# disc subcommands that wear the @report_output decorator and
# therefore benefit from `--as display` at capture time. Subcommands
# not on this list (`cat`, `type`, `freemap`, `put`, `get`, `cp`,
# `mv`, `rm`, `mkdir`, `chmod`, `lock`, `unlock`, `set-*`,
# `validate`, `create`, `compact`, `expand`, `afs-init`, `afs-merge`,
# etc.) reject `--as` — passing it would make the recipe fail.
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
        "afs-plan",
        "afs-users",
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
    return tokens[1] in _REPORT_SUBCOMMANDS


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
    """
    print(f"$ {command}")

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
