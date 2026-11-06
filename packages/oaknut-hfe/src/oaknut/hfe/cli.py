"""HFE contributed ``disc`` commands.

The ``disc hfe`` command group, contributed on the ``oaknut.command``
axis. Reading files from an HFE image needs none of these: every generic
command opens one through the decoder (see :mod:`oaknut.hfe.decoder`).
This group covers what only makes sense below the sector level: the
capture's header, a per-track, per-sector report for copy-protected
discs, and writing the flattened sector image out.

This module imports Click and is loaded only when ``oaknut-hfe`` is
installed with its ``[cli]`` extra; the library core never imports it.
"""

from __future__ import annotations

from pathlib import Path

import click
from asyoulikeit import Report, Reports, TableContent
from asyoulikeit.cli import report_output

_IMAGE = click.argument("image", type=click.Path(exists=True, dir_okay=False, path_type=Path))


@click.group()
def hfe() -> None:
    """HFE (HxC Floppy Emulator) flux-image tools."""


def _load(image: Path):
    from oaknut.hfe.container import HFEImage
    from oaknut.hfe.decode import decode_image
    from oaknut.hfe.flat import flatten

    hfe_image = HFEImage.from_filepath(image)
    disc = decode_image(hfe_image)
    return hfe_image, disc, flatten(disc)


@hfe.command(name="info")
@_IMAGE
@report_output(
    reports={
        "header": "The HFE header: what the capture tool recorded.",
        "layout": "The sector layout decoded from the tracks.",
    }
)
def info_command(image: Path):
    """Describe an HFE image: its header and the disc decoded from it.

    The header records how the disc was captured; the layout is what
    the tracks actually hold, inferred from the decoded sectors. They
    can differ: an 80-track capture of a 40-track disc, say.
    """
    from oaknut.cli import kv_table
    from oaknut.hfe.container import TrackEncoding

    hfe_image, _disc, flat = _load(image)
    header = hfe_image.header
    encoding = header.track_encoding
    header_table = kv_table(
        image.name,
        [
            ("version", "Version", header.version),
            ("tracks", "Tracks", header.num_tracks),
            ("sides", "Sides", header.num_sides),
            (
                "encoding",
                "Encoding",
                encoding.name if isinstance(encoding, TrackEncoding) else f"&{encoding:02X}",
            ),
            ("bitrate_kbps", "Bit rate (kbit/s)", header.bitrate_kbps),
            ("rpm", "RPM", header.rpm),
            ("interface_mode", "Interface mode", header.interface_mode),
            ("single_step", "Single step", "yes" if header.single_step else "no"),
        ],
    )
    layout = flat.layout
    if layout is None:
        layout_table = TableContent(title="Layout", description="no readable sectors")
    else:
        layout_table = kv_table(
            "Layout",
            [
                ("encoding", "Encoding", layout.encoding.value),
                ("tracks", "Tracks", layout.num_tracks),
                ("sides", "Sides", layout.num_sides),
                ("sectors_per_track", "Sectors per track", layout.sectors_per_track),
                ("sector_size", "Sector size", layout.sector_size),
                ("first_record", "First record", layout.first_record),
                ("double_stepped", "Double-stepped", "yes" if layout.double_stepped else "no"),
                ("unreadable", "Unreadable sectors", len(flat.missing)),
                ("suffix", "Sector image", flat.suffix or "-"),
            ],
        )
    return Reports(header=Report(data=header_table), layout=Report(data=layout_table))


@hfe.command(name="sectors")
@_IMAGE
@click.option("--track", "track_number", type=int, default=None, help="Report one physical track.")
@click.option(
    "--anomalies",
    is_flag=True,
    default=False,
    help="Report only tracks and sectors that depart from the disc's layout.",
)
@report_output(
    reports={
        "tracks": "Each physical track: sectors found, and what is unusual about it.",
        "sectors": "Each ID address mark found: C/H/R/N, CRCs, data mark, remarks.",
    }
)
def sectors_command(image: Path, track_number: int | None, anomalies: bool):
    """Report every track and sector decoded from an HFE image.

    Lists each ID address mark found on each physical track, whether or
    not a filesystem would use it: its cylinder, head, record and size
    code, its ID CRC, and its data field: ``ok``, ``bad CRC``,
    ``deleted`` (a deleted-data mark), or ``none``. Offsets count flux
    samples from the start of the track, 2 µs each at 250 kbit/s. Remarks
    name each departure from the disc's standard layout (IDs claiming
    another cylinder or head, records out of range, odd sizes, duplicates,
    CRC errors, deleted or missing data, weak bits, unformatted or extra
    tracks), which is how copy protection shows up. The side column
    appears only for a double-sided image.
    """
    from oaknut.hfe.report import analyse

    _hfe_image, disc, flat = _load(image)
    findings = analyse(disc, flat.layout)
    if track_number is not None:
        findings = tuple(f for f in findings if f.track == track_number)
    if anomalies:
        findings = tuple(f for f in findings if f.anomalous)

    tracks = TableContent(title=image.name)
    for key, label in (
        ("track", "Track"),
        ("side", "Side"),
        ("sectors", "Sectors"),
        ("readable", "Readable"),
        ("remarks", "Remarks"),
    ):
        tracks.add_column(key, label)
    double_sided = disc.num_sides == 2
    sectors = TableContent(title="Sectors")
    for key, label in (
        ("track", "Track"),
        *((("side", "Side"),) if double_sided else ()),
        ("offset", "Offset"),
        ("encoding", "Enc"),
        ("cylinder", "C"),
        ("head", "H"),
        ("record", "R"),
        ("size_code", "N"),
        ("id_crc", "ID CRC"),
        ("data", "Data"),
        ("remarks", "Remarks"),
    ):
        sectors.add_column(key, label)

    for finding in findings:
        decoded_sectors = finding.decoded.sectors
        tracks.add_row(
            track=finding.track,
            side=finding.side,
            sectors=len(decoded_sectors),
            readable=sum(sector.readable for sector in decoded_sectors),
            remarks="; ".join(finding.remarks),
        )
        for sector_finding in finding.sectors:
            if anomalies and not sector_finding.remarks:
                continue
            sector = sector_finding.sector
            sectors.add_row(
                track=finding.track,
                **({"side": finding.side} if double_sided else {}),
                offset=sector.position,
                encoding=sector.encoding.value,
                cylinder=sector.id.cylinder,
                head=sector.id.head,
                record=sector.id.record,
                size_code=sector.id.size_code,
                id_crc="ok" if sector.id_crc_ok else "bad",
                data=_data_field(sector),
                remarks="; ".join(sector_finding.remarks),
            )
    return Reports(tracks=Report(data=tracks), sectors=Report(data=sectors))


def _data_field(sector) -> str:
    """A sector's data field in a word or two: ok, bad CRC, deleted, none."""
    from oaknut.hfe.decode import DataMark

    if sector.data_mark is None:
        return "none"
    parts = []
    if sector.data_mark is DataMark.DELETED:
        parts.append("deleted")
    if not sector.data_crc_ok:
        parts.append("bad CRC")
    return ", ".join(parts) or "ok"


@hfe.command(name="flatten")
@_IMAGE
@click.argument("output", type=click.Path(dir_okay=False, path_type=Path))
@click.option(
    "--fill",
    default="0",
    show_default=True,
    help="Byte for sectors that could not be read (0x prefix for hex).",
)
@click.option("--force", is_flag=True, default=False, help="Overwrite OUTPUT if it exists.")
def flatten_command(image: Path, output: Path, fill: str, force: bool) -> None:
    """Write the sector image decoded from an HFE image to OUTPUT.

    The result is laid out like an .ssd, .dsd or .adl: each track's
    sectors in record order, the sides of a double-sided disc
    interleaved track by track. Sectors that could not be read are
    filled with the --fill byte and counted on stderr.
    """
    from oaknut.file import parse_address
    from oaknut.hfe.container import HFEImage
    from oaknut.hfe.decode import decode_image
    from oaknut.hfe.decoder import flat_image_notes
    from oaknut.hfe.exceptions import HFEError
    from oaknut.hfe.flat import flatten

    fill_byte = parse_address(fill)
    if not 0 <= fill_byte <= 0xFF:
        raise click.BadParameter(f"{fill!r} is not a byte value", param_hint="--fill")
    if output.exists() and not force:
        raise click.ClickException(f"{output} exists; pass --force to overwrite it")
    flat = flatten(decode_image(HFEImage.from_filepath(image)), fill=fill_byte)
    if flat.layout is None:
        raise HFEError(f"no readable sectors in {image.name}")
    if flat.suffix and output.suffix.lower() != flat.suffix:
        click.echo(f"note: this layout is conventionally a {flat.suffix} image", err=True)
    output.write_bytes(flat.data)
    for note in flat_image_notes(flat):
        click.echo(note, err=True)
