"""ADFS-family contributed ``disc`` commands.

The ``disc adfs`` command group, contributed to the CLI on the
``oaknut.command`` axis (see ``docs/dev/contributed-commands.md``). It
holds ADFS-specific administration that does not fit the generic mount
model — currently ``disc adfs generate-dsc``.

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
    from oaknut.adfs.free_space_map import OldFreeSpaceMap
    from oaknut.discimage.surface import DiscImage, SurfaceSpec
    from oaknut.discimage.unified_disc import UnifiedDisc

    if image.suffix.lower() != ".dat":
        raise click.ClickException(f"image must have a .dat extension, got '{image.suffix}'")

    dsc_filepath = image.with_suffix(".dsc")
    if dsc_filepath.exists() and not force:
        raise click.ClickException(f"refusing to overwrite existing '{dsc_filepath}'; pass --force")

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

    total_sectors = fsm.total_sectors
    if total_sectors == 0:
        raise click.ClickException(
            "image does not parse as an ADFS Old Map: total disc size is zero"
        )
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
        f"total={total_sectors} sectors / {fsm.total_size:,} bytes)"
    )

    file_sectors = len(data) // 256
    if file_sectors < total_sectors:
        click.echo(
            f"note: image is truncated to {file_sectors:,} sectors "
            f"({len(data):,} bytes) but the FSM declares {total_sectors:,} "
            f"sectors. Reads of the present prefix work; allocations need "
            f"a padded image.",
            err=True,
        )
