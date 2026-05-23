"""Sphinx extension: ``.. oaknut-command::`` directive.

A drop-in replacement for ``.. click::`` (sphinx-click) that renders
one Click command using semantic doctree nodes — definition lists for
Arguments / Options / Reports rather than nested literal blocks — so
the resulting HTML is a real ``<dl>`` of code-font terms and
descriptions instead of full-width grey backgrounds.

Usage in a documentation page:

  .. oaknut-command:: oaknut.disc.cli:opt
     :prog: disc opt

     Reading the current value:

     .. cli-example:: cmd_opt
        :section: read

     Setting numerically:

     .. cli-example:: cmd_opt
        :section: set_numeric

The directive body is parsed as RST and emitted under an
"Examples" rubric after the auto-generated structural sections.
This lets a command page weave runnable transcripts inline with
the introspected reference.

Sections emitted (in order):
  description     — first paragraph(s) of the command's docstring
                    (everything before any ``\\f`` form-feed; the
                    asyoulikeit "Produces reports:" epilog is
                    stripped because we render it separately).
  Usage           — synthesised ``prog [OPTIONS] ARG [ARG…]`` line.
  Arguments       — definition list, code-font argument metavar +
                    required/optional qualifier in the term.
  Options         — definition list, code-font option spellings +
                    type / metavar in the term, help text in the
                    definition.
  Reports         — definition list, code-font report name in the
                    term, description in the definition (only when
                    the command was wrapped with
                    ``@asyoulikeit.cli.report_output``).
  Acorn aliases   — comma-separated ``*ALIAS`` codes that route to
                    this command via the project's ``AliasGroup``
                    (only when at least one alias is registered).
  Examples        — directive body parsed as RST (only when the
                    directive has body content).
"""

from __future__ import annotations

import importlib
import inspect
import re
from typing import Any

import click
from docutils import nodes
from docutils.parsers.rst import directives
from docutils.statemachine import StringList
from sphinx.application import Sphinx
from sphinx.util.docutils import SphinxDirective


# ---------------------------------------------------------------------------
# Public registration
# ---------------------------------------------------------------------------


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_directive("oaknut-command", OaknutCommandDirective)
    return {
        "version": "1.0",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }


# ---------------------------------------------------------------------------
# Command resolution + docstring slicing
# ---------------------------------------------------------------------------


_REPORTS_EPILOG_RE = re.compile(
    r"\n+\x08\nProduces reports:\n(?:  .*\n?)+",
    re.MULTILINE,
)


# Options injected by the asyoulikeit @report_output decorator. We keep
# --as visible on every command — it's the format selector users actually
# reach for — and fold the rest into a single cross-reference note so the
# Options list does not duplicate the same five entries on twenty-odd
# subcommands.
_HIDDEN_REPORT_OUTPUT_OPTS = frozenset(
    {
        "--no-reports",
        "--all-reports",
        "--report",
        "--header",
        "--detailed",
    }
)

_REPORT_OUTPUT_NOTE_RST = (
    "The standard report-output flags — "
    "``--report``, ``--no-reports``, ``--all-reports``, "
    "``--header``/``--no-header``, "
    "``--detailed``/``--essential`` — are also accepted; "
    "see :doc:`/cli/conventions/output-formats`."
)


def _is_hidden_report_output_option(opt: click.Option) -> bool:
    return any(name in _HIDDEN_REPORT_OUTPUT_OPTS for name in opt.opts)


def _resolve_command(target: str) -> click.Command:
    """Resolve ``module.path:attr.chain`` to a Click command."""
    module_path, _, attr = target.partition(":")
    if not module_path or not attr:
        raise ValueError(
            f"oaknut-command target must be 'module:attr', got {target!r}"
        )
    module = importlib.import_module(module_path)
    obj: Any = module
    for part in attr.split("."):
        obj = getattr(obj, part)
    if not isinstance(obj, click.Command):
        raise TypeError(
            f"{target} resolved to {type(obj).__name__}, not click.Command"
        )
    return obj


def _strip_click_markers(text: str) -> str:
    """Drop Click's ``\\b`` (no-rewrap) markers from a stand-alone string.

    Used for option / report help text where the marker may slip in but
    there is no block-level transform to apply. For the command-level
    description, prefer :func:`_convert_b_blocks` which preserves line
    breaks by rewriting the marked block as an RST line block.
    """
    return text.replace("\x08", "")


_ACORN_STAR_RE = re.compile(r"(?<![\w`])(\*[A-Z][A-Z0-9_]*)")
_OPTION_TOKEN_RE = re.compile(r"(?<![\w`-])(--?[A-Za-z][\w-]*)")


def _convert_b_blocks(text: str) -> str:
    """Rewrite Click ``\\b``-marked no-rewrap blocks as RST line blocks.

    Click uses ``\\b`` (ASCII backspace, on its own line) to mark the
    start of a paragraph the plain-text formatter should not rewrap —
    typically a small aligned table like the boot-option enum. The
    natural RST equivalent is a line block (``| line``) which preserves
    the source's line breaks under HTML rendering.
    """
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == "\x08":
            block: list[str] = []
            j = i + 1
            while j < len(lines) and lines[j].strip():
                block.append(lines[j])
                j += 1
            if out and out[-1] != "":
                out.append("")
            for block_line in block:
                out.append("| " + block_line)
            if j < len(lines):
                out.append("")
            i = j
        else:
            out.append(line.replace("\x08", ""))
            i += 1
    return "\n".join(out)


def _escape_acorn_stars(text: str) -> str:
    """Wrap Acorn ``*COMMAND`` references in inline literal markup.

    Without this, the leading ``*`` is misread by docutils as an
    emphasis marker, producing ``<span class="problematic">*</span>``
    in the HTML. Acorn star commands are always ``*`` followed by an
    uppercase token, so the heuristic is unambiguous.
    """
    return _ACORN_STAR_RE.sub(r"``\1``", text)


def _extract_description(help_text: str | None) -> str:
    """Return the docstring head suitable for RST rendering.

    Strips:
      - Everything from ``\\f`` onwards (Click's truncation marker).
      - The asyoulikeit ``Produces reports:`` line block (rendered separately).

    Rewrites:
      - ``\\b`` no-rewrap blocks into RST line blocks (line breaks preserved).
      - ``*COMMAND`` Acorn references into RST inline literals.
    """
    if not help_text:
        return ""
    head = help_text.split("\f", 1)[0]
    head = _REPORTS_EPILOG_RE.sub("\n", head)
    head = inspect.cleandoc(head)
    head = _convert_b_blocks(head)
    head = _escape_acorn_stars(head)
    return head


def _find_reports(command: click.Command) -> dict | None:
    """Locate the ``_asyoulikeit_reports`` dict on the command's callback chain."""
    callback = command.callback
    while callback is not None:
        reports = getattr(callback, "_asyoulikeit_reports", None)
        if reports:
            return reports
        callback = getattr(callback, "__wrapped__", None)
    return None


def _find_acorn_aliases(command: click.Command) -> list[str]:
    """Reverse-lookup Acorn star-aliases pointing at *command*.

    Uses :data:`oaknut.disc.cli._ALIASES` if available — the module-level
    ``{star_name: unix_name}`` dict populated by ``_alias()`` calls.
    """
    try:
        from oaknut.disc.cli import _ALIASES
    except ImportError:
        return []
    name = command.name
    return sorted(star for star, unix in _ALIASES.items() if unix == name)


# ---------------------------------------------------------------------------
# Term builders
# ---------------------------------------------------------------------------


def _format_type_hint(param: click.Parameter) -> str | None:
    """Return a short label for *param*'s type, or None for plain flags."""
    if isinstance(param, click.Option) and param.is_flag:
        return None
    t = param.type
    if isinstance(t, click.Choice):
        return "[" + "|".join(t.choices) + "]"
    if isinstance(t, click.IntRange):
        lo = "" if t.min is None else str(t.min)
        hi = "" if t.max is None else str(t.max)
        return f"int [{lo}..{hi}]"
    if t is click.STRING:
        return "TEXT"
    if t is click.INT:
        return "INT"
    if t is click.FLOAT:
        return "FLOAT"
    if t is click.BOOL:
        return "BOOL"
    # Custom ParamType — fall back to its `name` attribute.
    name = getattr(t, "name", None)
    if name:
        return name.upper()
    return None


def _build_argument_term(arg: click.Argument) -> nodes.term:
    """Term node for an argument: ``METAVAR`` (optional) (nargs=N)."""
    term = nodes.term()
    metavar = arg.metavar or arg.name.upper()
    term += nodes.literal(text=metavar)
    qualifiers = []
    if not arg.required:
        qualifiers.append("optional")
    if arg.nargs != 1:
        qualifiers.append(f"nargs={arg.nargs}")
    if qualifiers:
        term += nodes.Text(" (" + ", ".join(qualifiers) + ")")
    return term


def _build_option_term(opt: click.Option) -> nodes.term:
    """Term node for an option.

    Examples of the rendered shape (everything in code font is a
    ``<code>``; everything else is plain text):

      ``--report`` ``TEXT``
      ``--header`` / ``--no-header``
      ``-a``, ``--all-reports``
      ``--as`` ``[display|json|tsv]``
    """
    term = nodes.term()
    primary = list(opt.opts)
    for i, name in enumerate(primary):
        if i > 0:
            term += nodes.Text(", ")
        term += nodes.literal(text=name)
    for neg in opt.secondary_opts:
        term += nodes.Text(" / ")
        term += nodes.literal(text=neg)
    hint = _format_type_hint(opt)
    if hint and not opt.secondary_opts:
        term += nodes.Text(" ")
        term += nodes.literal(text=hint)
    return term


def _build_description_paragraph(text: str) -> nodes.paragraph:
    """Build a paragraph that renders option-like tokens in code font.

    Two concerns covered by this routine:

    * Mentions of ``--report`` or ``-x`` in the help text would otherwise
      be smartquoted into ``–report`` (en-dash) by docutils. Wrapping
      them in :class:`nodes.literal` both inhibits the transform and
      gives the reference code-font emphasis.
    * Acorn ``*CAT``-style references are wrapped for the same reason
      (the leading ``*`` would otherwise be read as emphasis markup).
    """
    clean = _strip_click_markers(text)
    clean = re.sub(r"\s+", " ", clean).strip()

    para = nodes.paragraph()
    pos = 0
    pattern = re.compile(
        rf"{_OPTION_TOKEN_RE.pattern}|{_ACORN_STAR_RE.pattern}"
    )
    for match in pattern.finditer(clean):
        if match.start() > pos:
            para += nodes.Text(clean[pos:match.start()])
        para += nodes.literal(text=match.group(0))
        pos = match.end()
    if pos < len(clean):
        para += nodes.Text(clean[pos:])
    return para


def _build_deflist_item(
    term: nodes.term, description: str | None
) -> nodes.definition_list_item:
    item = nodes.definition_list_item()
    item += term
    definition = nodes.definition()
    if description:
        definition += _build_description_paragraph(description)
    item += definition
    return item


# ---------------------------------------------------------------------------
# Directive
# ---------------------------------------------------------------------------


class OaknutCommandDirective(SphinxDirective):
    has_content = True
    required_arguments = 1
    final_argument_whitespace = False
    option_spec = {
        "prog": directives.unchanged,
        "title": directives.unchanged,
        "hide-arguments": directives.flag,
        "hide-options": directives.flag,
    }

    # -----------------------------------------------------------------
    # Top-level entry point
    # -----------------------------------------------------------------

    def run(self) -> list[nodes.Node]:
        target = self.arguments[0]
        try:
            command = _resolve_command(target)
        except (ImportError, AttributeError, TypeError, ValueError) as exc:
            error = self.state.document.reporter.error(
                f"oaknut-command: could not resolve {target!r}: {exc}",
                line=self.lineno,
            )
            return [error]

        prog = self.options.get("prog") or command.name
        title_text = self.options.get("title") or command.name

        section = nodes.section()
        section["ids"] = [
            nodes.make_id(f"oaknut-command-{prog.replace(' ', '-')}")
        ]
        section += nodes.title(text=title_text)

        # 1. Description.
        description = _extract_description(command.help)
        if description:
            self._append_rst(section, description)

        # 2. Usage.
        section += nodes.rubric(text="Usage")
        usage_text = self._build_usage_line(prog, command)
        usage_node = nodes.literal_block(usage_text, usage_text)
        usage_node["language"] = "shell"
        section += usage_node

        # 3. Arguments.
        args = [
            p for p in command.params
            if isinstance(p, click.Argument)
        ]
        if args and "hide-arguments" not in self.options:
            section += nodes.rubric(text="Arguments")
            section += self._build_arguments_deflist(args)

        # 4. Options.
        all_opts = [
            p for p in command.params
            if isinstance(p, click.Option) and not p.hidden
        ]
        visible_opts = [
            o for o in all_opts
            if not _is_hidden_report_output_option(o)
        ]
        has_hidden_report_opts = any(
            _is_hidden_report_output_option(o) for o in all_opts
        )
        if (visible_opts or has_hidden_report_opts) and "hide-options" not in self.options:
            section += nodes.rubric(text="Options")
            if visible_opts:
                section += self._build_options_deflist(visible_opts)
            if has_hidden_report_opts:
                self._append_rst(section, _REPORT_OUTPUT_NOTE_RST)

        # 5. Reports.
        reports = _find_reports(command)
        if reports:
            section += nodes.rubric(text="Reports")
            section += self._build_reports_deflist(reports)

        # 6. Acorn aliases.
        aliases = _find_acorn_aliases(command)
        if aliases:
            section += nodes.rubric(text="Acorn aliases")
            section += self._build_aliases_paragraph(aliases)

        # 7. Examples (directive body).
        if self.content:
            section += nodes.rubric(text="Examples")
            self._append_body(section)

        return [section]

    # -----------------------------------------------------------------
    # Builders for each section
    # -----------------------------------------------------------------

    def _build_usage_line(self, prog: str, command: click.Command) -> str:
        parts = [prog]
        has_options = any(
            isinstance(p, click.Option) and not p.hidden
            for p in command.params
        )
        if has_options:
            parts.append("[OPTIONS]")
        for arg in command.params:
            if not isinstance(arg, click.Argument):
                continue
            metavar = arg.metavar or arg.name.upper()
            if arg.nargs == -1:
                token = f"[{metavar}...]"
            elif arg.required:
                token = metavar
            else:
                token = f"[{metavar}]"
            parts.append(token)
        return " ".join(parts)

    def _build_arguments_deflist(
        self, args: list[click.Argument]
    ) -> nodes.definition_list:
        dl = nodes.definition_list()
        for arg in args:
            term = _build_argument_term(arg)
            # Click arguments rarely carry help text; fall through to the
            # command-level docstring for the explanation. If we ever
            # attach descriptions via metadata, surface them here.
            description = getattr(arg, "help", None)
            dl += _build_deflist_item(term, description)
        return dl

    def _build_options_deflist(
        self, opts: list[click.Option]
    ) -> nodes.definition_list:
        dl = nodes.definition_list()
        for opt in opts:
            term = _build_option_term(opt)
            dl += _build_deflist_item(term, opt.help)
        return dl

    def _build_reports_deflist(self, reports: dict) -> nodes.definition_list:
        dl = nodes.definition_list()
        for name, description in reports.items():
            term = nodes.term()
            display_name = "<dynamic>" if name is Ellipsis else str(name)
            term += nodes.literal(text=display_name)
            dl += _build_deflist_item(term, description)
        return dl

    def _build_aliases_paragraph(self, aliases: list[str]) -> nodes.paragraph:
        para = nodes.paragraph()
        for i, alias in enumerate(aliases):
            if i > 0:
                para += nodes.Text(", ")
            para += nodes.literal(text=alias)
        return para

    # -----------------------------------------------------------------
    # RST parsing helpers
    # -----------------------------------------------------------------

    def _append_rst(self, parent: nodes.Element, text: str) -> None:
        """Parse *text* as RST and append the resulting children to *parent*."""
        view = StringList()
        for i, line in enumerate(text.splitlines()):
            view.append(line, source=f"<oaknut-command:{self.lineno}>", offset=i)
        scratch = nodes.section()
        self.state.nested_parse(view, 0, scratch)
        for child in list(scratch.children):
            parent += child

    def _append_body(self, parent: nodes.Element) -> None:
        """Parse the directive's body content and append it to *parent*."""
        scratch = nodes.section()
        self.state.nested_parse(self.content, self.content_offset, scratch)
        for child in list(scratch.children):
            parent += child
