"""CLI commands for content-based disc-image identification.

``identify`` reports what an image actually is — by reading its bytes,
not by trusting its extension — best guess first, with evidence. The
``list-filesystems`` / ``describe-filesystem`` pair introspects the
filesystem axis: which filesystems this build can recognise, and what
each one is. (The ``--as`` output formatters are a separate axis,
introspected by ``list-report-formats`` / ``describe-report-format``.)

All three draw on the :mod:`oaknut.filesystem` coordinator: every
installed filesystem package contributes its own detector, so the set
grows automatically with what is installed. Each is a factory returning
a Click command so the host group assigns the final name.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import click
from asyoulikeit import Report, Reports, ScalarContent, TableContent
from asyoulikeit.cli import report_output
from oaknut.file.capacity import format_capacity
from oaknut.filesystem import (
    FLOPPY,
    WINCHESTER,
    Identification,
    create_filesystem,
    describe_filesystem,
    filesystem_names,
    identify,
)


def _flatten(
    candidates: tuple[Identification, ...] | list[Identification],
) -> Iterator[Identification]:
    """Walk an identification tree depth-first, parents before children.

    A combined disc — an ADFS host with an AFS tail — is a parent with
    its tail in :attr:`Identification.contained`; flattening yields one
    row per region.
    """
    for candidate in candidates:
        yield candidate
        yield from _flatten(candidate.contained)


def identify_command() -> click.Command:
    """A command that identifies a disc image's filesystem(s) by content."""

    @click.command()
    @click.argument(
        "image_filepath",
        type=click.Path(exists=True, dir_okay=False, path_type=Path),
    )
    @report_output(
        reports={"candidates": "Ranked filesystem-identification candidates with evidence."}
    )
    def identify_image(image_filepath: Path):
        """Identify a disc image's filesystem(s) by content, best guess first.

        Reads the image rather than trusting its file extension, so it
        works even when the name is missing or wrong. Each candidate
        carries a confidence level — from CERTAIN (an unambiguous magic
        number) down to POSSIBLE — and the evidence behind it. A
        combined disc, such as an ADFS hard disc hosting an AFS tail
        partition, yields more than one row.
        """
        candidates = list(_flatten(identify(image_filepath)))
        table = TableContent(
            title=image_filepath.name,
            description=None if candidates else "no known filesystem recognised",
        )
        table.add_column("confidence", "Confidence")
        table.add_column("filesystem", "Filesystem")
        table.add_column("partition", "Partition")
        table.add_column("evidence", "Evidence")
        for candidate in candidates:
            partition = candidate.partition.selector if candidate.partition else ""
            table.add_row(
                confidence=candidate.confidence.name,
                filesystem=candidate.filesystem or "(unidentified)",
                partition=partition,
                evidence="; ".join(candidate.evidence),
            )
        return Reports(candidates=Report(data=table))

    return identify_image


def list_filesystems_command() -> click.Command:
    """A command that lists the filesystems this build can recognise."""

    @click.command()
    @report_output(reports={"filesystems": "Filesystems this build can recognise."})
    def list_filesystems():
        """List the filesystems this build can recognise."""
        table = TableContent(title="Recognised filesystems")
        table.add_column("name", "Name")
        table.add_column("description", "Description")
        for name in sorted(filesystem_names()):
            table.add_row(
                name=name, description=describe_filesystem(name, single_line=True)
            )
        return Reports(filesystems=Report(data=table))

    return list_filesystems


def _geometry_table(name: str) -> TableContent:
    """The geometries a filesystem accepts for ``disc create --geometry``.

    One row per named preset (with the image size it yields), plus a row
    per parameterised form the filesystem's grammar admits.
    """
    grammar = create_filesystem(name).geometry_grammar()
    has_any = bool(grammar.preset_names()) or bool(grammar.kinds)
    table = TableContent(
        title="Geometries (--geometry)",
        description=None if has_any else "this filesystem has no geometry",
    )
    table.add_column("spec", "--geometry")
    table.add_column("result", "Result")
    for preset in grammar.preset_names():
        table.add_row(spec=preset, result=format_capacity(grammar.presets[preset].image_size))
    if WINCHESTER in grammar.kinds:
        table.add_row(spec="capacity=SIZE", result="hard disc of the given size")
        table.add_row(spec="cylinders=N,heads=N,spt=N", result="hard disc, explicit geometry")
    if FLOPPY in grammar.kinds:
        table.add_row(
            spec="tracks=N,sides=N[,interleave=interleaved|sequential]",
            result="custom floppy",
        )
    return table


def describe_filesystem_command() -> click.Command:
    """A command that prints one recognised filesystem's full description."""

    @click.command()
    @click.argument(
        "name", type=click.Choice(sorted(filesystem_names()), case_sensitive=False)
    )
    @report_output(
        reports={
            "filesystem": "The full description of one recognised filesystem.",
            "geometries": "The geometries it accepts for `disc create --geometry`.",
        }
    )
    def describe_filesystem_cmd(name: str):
        """Describe one recognised filesystem in detail.

        Includes the geometries it accepts for ``disc create --geometry``
        — the named presets and any parameterised (capacity / CHS /
        floppy) forms.
        """
        return Reports(
            filesystem=Report(data=ScalarContent(value=describe_filesystem(name), title=name)),
            geometries=Report(data=_geometry_table(name)),
        )

    return describe_filesystem_cmd
