"""ADFS-family contributed ``disc`` commands.

The ``disc adfs`` command group, contributed to the CLI on the
``oaknut.command`` axis (see ``docs/dev/contributed-commands.md``). It
holds ADFS-specific administration that does not fit the generic mount
model — currently ``disc adfs generate-dsc`` and ``disc adfs generate-cfg``.

This module imports Click and is loaded only when ``oaknut-adfs`` is
installed with its ``[cli]`` extra; the ADFS library core never imports it.
"""

from __future__ import annotations

from pathlib import Path

import click

# Defaults match the RetroClinic Data Centre IDE/CF interface, which is
# the most common situation in which a .dat arrives with no .dsc — the
# Windows cfbackup utility doesn't ship one. The patched ADFS ROM
# initialises the IDE drive with INITIALIZE DEVICE PARAMETERS (heads=4,
# sectors-per-track=64). See docs/dev/analysis/data-centre/ for the
# disassembly evidence.
_DEFAULT_HEADS = 4
_DEFAULT_SPT = 64

# The BeebSCSI/Pi1MHz firmware assumes SCSI sectors-per-track of 33 and,
# absent an explicit head count, derives heads as the largest divisor of
# the track count that is <= 16 (mirroring filesystemCreateDscFromLunImage).
_SCSI_SPT = 33
_MAX_DERIVED_HEADS = 16


def _old_map_total_sectors(image: Path) -> tuple[int, int]:
    """The disc's total sector count from the ADFS Old Map at *image*'s head.

    Returns ``(total_sectors, file_sectors)``. Raises ``click.ClickException``
    when *image* is not a ``.dat``, is too small, or does not parse as an
    Old Map.
    """
    from oaknut.adfs.free_space_map import OldFreeSpaceMap
    from oaknut.discimage.surface import DiscImage, SurfaceSpec
    from oaknut.discimage.unified_disc import UnifiedDisc

    if image.suffix.lower() != ".dat":
        raise click.ClickException(f"image must have a .dat extension, got '{image.suffix}'")

    data = image.read_bytes()
    if len(data) < 512:
        raise click.ClickException(
            f"image is too small ({len(data)} bytes) to contain an ADFS old map"
        )
    if len(data) % 256 != 0:
        raise click.ClickException(f"image size ({len(data)} bytes) is not a multiple of 256")

    spec = SurfaceSpec(
        num_tracks=1,
        sectors_per_track=len(data) // 256,
        bytes_per_sector=256,
        track_zero_offset_bytes=0,
        track_stride_bytes=len(data),
    )
    sectors = UnifiedDisc(DiscImage(memoryview(data), [spec])).sector_range(0, 2)
    try:
        fsm = OldFreeSpaceMap(sectors)
    except Exception as exc:
        raise click.ClickException(f"image does not parse as an ADFS Old Map: {exc}") from exc

    if fsm.total_sectors == 0:
        raise click.ClickException(
            "image does not parse as an ADFS Old Map: total disc size is zero"
        )
    return fsm.total_sectors, len(data) // 256


def _truncation_note(file_sectors: int, total_sectors: int, image_bytes: int) -> None:
    """Warn on stderr when *image* is a truncated prefix of its FSM extent."""
    if file_sectors < total_sectors:
        click.echo(
            f"note: image is truncated to {file_sectors:,} sectors "
            f"({image_bytes:,} bytes) but the FSM declares {total_sectors:,} "
            f"sectors. Reads of the present prefix work; allocations need "
            f"a padded image.",
            err=True,
        )


@click.group()
def adfs() -> None:
    """ADFS administration (floppies and hard discs)."""


@adfs.command(name="generate-dsc")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--heads",
    type=click.IntRange(1, 16),
    default=_DEFAULT_HEADS,
    show_default=True,
    help="Number of heads in the synthesised geometry.",
)
@click.option(
    "--sectors-per-track",
    "spt",
    type=click.IntRange(1, 255),
    default=_DEFAULT_SPT,
    show_default=True,
    help="Sectors per track in the synthesised geometry.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing .dsc next to the image.",
)
def generate_dsc(image: Path, heads: int, spt: int, force: bool) -> None:
    """Write a ``.dsc`` geometry sidecar for an ADFS hard-disc ``.dat``.

    The total disc size is read from the ADFS Old Map at the head of
    the image. Cylinders are derived as ``total_sectors / (heads × spt)``
    and the resulting geometry is written to a 22-byte ``.dsc`` next to
    the image so that subsequent ``disc`` commands (``ls``, ``cat``, …)
    can open the image via ``ADFS.from_file``.

    Defaults to the RetroClinic Data Centre IDE geometry
    (``--heads 4 --sectors-per-track 64``); override for SCSI or other
    interfaces.
    """
    from oaknut.adfs import ADFSGeometry, write_dsc

    dsc_filepath = image.with_suffix(".dsc")
    if dsc_filepath.exists() and not force:
        raise click.ClickException(f"refusing to overwrite existing '{dsc_filepath}'; pass --force")

    total_sectors, file_sectors = _old_map_total_sectors(image)
    sectors_per_cylinder = heads * spt
    if total_sectors % sectors_per_cylinder != 0:
        raise click.ClickException(
            f"FSM total ({total_sectors} sectors) is not a multiple of "
            f"heads×spt ({heads}×{spt} = {sectors_per_cylinder}); pick a "
            f"different geometry"
        )
    cylinders = total_sectors // sectors_per_cylinder
    if cylinders < 1 or cylinders > 0xFFFF:
        raise click.ClickException(f"derived cylinders ({cylinders}) out of range 1..65535")

    geometry = ADFSGeometry(cylinders=cylinders, heads=heads, sectors_per_track=spt)
    write_dsc(dsc_filepath, geometry)

    click.echo(
        f"Wrote {dsc_filepath} "
        f"(cylinders={cylinders}, heads={heads}, sectors_per_track={spt}, "
        f"total={total_sectors} sectors / {total_sectors * 256:,} bytes)"
    )
    _truncation_note(file_sectors, total_sectors, image.stat().st_size)


@adfs.command(name="generate-cfg")
@click.argument("image", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--heads",
    type=click.IntRange(1, 16),
    default=None,
    help="Number of heads. Derived from the disc size when omitted.",
)
@click.option(
    "--sectors-per-track",
    "spt",
    type=click.IntRange(1, 255),
    default=_SCSI_SPT,
    show_default=True,
    help="Sectors per track in the synthesised geometry.",
)
@click.option(
    "--title",
    "disc_title",
    default="",
    help="Disc title recorded in the .cfg (Title= key).",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite an existing .cfg next to the image.",
)
def generate_cfg(image: Path, heads: int | None, spt: int, disc_title: str, force: bool) -> None:
    """Write a BeebSCSI/Pi1MHz ``.cfg`` sidecar for an ADFS hard-disc ``.dat``.

    The richer counterpart to ``generate-dsc``: its SCSI mode pages record
    sectors-per-track, so the file drops onto a Pi1MHz SD card (as
    ``BeebSCSI<n>/scsiN.cfg``) with its true geometry rather than the ``.dsc``
    default of 33.

    The total disc size is read from the ADFS Old Map. Defaults follow the
    BeebSCSI convention: ``--sectors-per-track 33``, and heads derived as the
    largest divisor of the track count that is at most 16. Pass ``--heads``
    to fix the head count instead.
    """
    from oaknut.adfs import ADFSGeometry, write_cfg

    cfg_filepath = image.with_suffix(".cfg")
    if cfg_filepath.exists() and not force:
        raise click.ClickException(f"refusing to overwrite existing '{cfg_filepath}'; pass --force")

    total_sectors, file_sectors = _old_map_total_sectors(image)
    if total_sectors % spt != 0:
        raise click.ClickException(
            f"FSM total ({total_sectors} sectors) is not a multiple of "
            f"sectors-per-track ({spt}); pick a different geometry"
        )
    tracks = total_sectors // spt

    if heads is None:
        heads = min(_MAX_DERIVED_HEADS, tracks)
        while tracks % heads != 0 and heads > 1:
            heads -= 1
    elif tracks % heads != 0:
        raise click.ClickException(
            f"track count ({tracks}) is not a multiple of heads ({heads}); "
            f"pick a different geometry"
        )
    cylinders = tracks // heads
    if cylinders < 1 or cylinders > 0xFFFF:
        raise click.ClickException(f"derived cylinders ({cylinders}) out of range 1..65535")

    geometry = ADFSGeometry(cylinders=cylinders, heads=heads, sectors_per_track=spt)
    write_cfg(cfg_filepath, geometry, title=disc_title)

    click.echo(
        f"Wrote {cfg_filepath} "
        f"(cylinders={cylinders}, heads={heads}, sectors_per_track={spt}, "
        f"total={total_sectors} sectors / {total_sectors * 256:,} bytes)"
    )
    _truncation_note(file_sectors, total_sectors, image.stat().st_size)
