"""CLI commands for content-based disc-image identification.

``identify`` reports what an image actually is — by reading its bytes,
not by trusting its extension — best guess first, with evidence. The
``list-formats`` / ``describe-format`` pair introspects the prober axis,
mirroring asyoulikeit's ``list-report-formats`` / ``describe-report-format``
(the names are qualified because "format" is overloaded in this CLI:
disc formats here, output formats there).

Each is a factory returning a Click command so the host group assigns
the final name, and ``prober_names()`` is evaluated at mount time —
any installed format package contributes its detector automatically.
"""

from __future__ import annotations

from pathlib import Path

import click
from asyoulikeit import Report, Reports, ScalarContent, TableContent
from asyoulikeit.cli import report_output
from oaknut.identify import describe_prober, identify, prober_names


def identify_command() -> click.Command:
    """A command that identifies a disc image's format(s) by content."""

    @click.command()
    @click.argument(
        "image_filepath",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
    )
    @report_output(
        reports={"candidates": "Ranked format-identification candidates with evidence."}
    )
    def identify_image(image_filepath: Path):
        """Identify a disc image's format(s) by content, best guess first.

        Reads the image rather than trusting its file extension, so it
        works even when the name is missing or wrong. Each candidate
        carries a confidence level — from CERTAIN (an unambiguous magic
        number) down to POSSIBLE — and the evidence behind it. A
        combined disc, such as an ADFS hard disc hosting an AFS tail
        partition, yields more than one row.
        """
        candidates = identify(image_filepath)
        table = TableContent(
            title=image_filepath.name,
            description=None if candidates else "no known disc format recognised",
        )
        table.add_column("confidence", "Confidence")
        table.add_column("family", "Family")
        table.add_column("detector", "Detector")
        table.add_column("evidence", "Evidence")
        for candidate in candidates:
            table.add_row(
                confidence=candidate.confidence.name,
                family=candidate.family,
                detector=candidate.prober_name,
                evidence="; ".join(candidate.evidence),
            )
        return Reports(candidates=Report(data=table))

    return identify_image


def list_formats_command() -> click.Command:
    """A command that lists the disc formats the identifier can recognise."""

    @click.command()
    @report_output(reports={"formats": "Disc formats this tool can recognise."})
    def list_formats():
        """List the disc formats the identifier can recognise."""
        table = TableContent(title="Recognised disc formats")
        table.add_column("name", "Name")
        table.add_column("description", "Description")
        for name in sorted(prober_names()):
            table.add_row(name=name, description=describe_prober(name, single_line=True))
        return Reports(formats=Report(data=table))

    return list_formats


def describe_format_command() -> click.Command:
    """A command that prints one recognised disc format's full description."""

    @click.command()
    @click.argument(
        "name", type=click.Choice(sorted(prober_names()), case_sensitive=False)
    )
    @report_output(reports={"format": "The full description of one recognised disc format."})
    def describe_format(name: str):
        """Describe one recognised disc format in detail."""
        return Reports(
            format=Report(data=ScalarContent(value=describe_prober(name), title=name))
        )

    return describe_format
