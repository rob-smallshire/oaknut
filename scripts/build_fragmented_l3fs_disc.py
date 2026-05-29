"""Build an L3FS disc image whose AFS partition contains a heavily
fragmented file with chained map sectors.

The goal is to produce an image that exercises the chain-pointer path
(slot 48 of a map block carrying ``(next_block_SIN, 1)``) **plus** a
successor map block that lacks the ``'JesMap'`` magic at offsets
0..5. Per the L3V126 ROM (see ``docs/dev/afs-onwire.md``), the magic
is written only by ``MPCRSP`` on the initial map block of an object;
``MKRLN``'s successor-allocation path allocates a sector, clears the
cache buffer via ``CLRSTR``, populates extents from offset 10, and
never invokes the magic-write loop. So the second and later blocks
of a chain land on disc with zeros at 0..5.

Loading this image into a real L3FS — for example, a BBC running the
file-server ROM against an emulated SCSI volume — and reading the
fragmented file is a direct check on that ROM-behaviour claim. If the
server returns the file's bytes intact, the magic really is head-only
and the parser correctly walks the chain without inspecting offsets
0..5 of the successor.

The script mirrors the bootable-disc cookbook recipe:

1. Create an empty ADFS hard-disc envelope.
2. Copy the FS3 binary off ``FS3v126.ssd`` onto the ADFS partition.
3. Write ``!BOOT`` containing ``*RUN $.FS3v126<CR>`` and set the boot
   option to ``EXEC``.
4. Initialise the AFS partition.
5. Pre-fragment the AFS bitmap by marking interleaved sectors of every
   cylinder as allocated. This forces the allocator into many short
   free runs.
6. Write one large file (``Frag``) that consumes enough of the
   fragmented free space to overflow 48 coalesced extents.
7. Verify on-disc shape: the file's map chain has more than one block;
   the head block carries ``'JesMap'`` at 0..5; every successor block
   carries zeros there.

Usage::

    uv run python scripts/build_fragmented_l3fs_disc.py \\
        --output /tmp/fragmented.dat \\
        --fs-binary tests/data/images/cookbook/FS3v126.ssd

If ``--fs-binary`` is omitted, the cookbook's ``FS3v126.ssd`` is used.
The output is a ``.dat`` SCSI hard-disc image plus a companion
``.dsc`` sidecar; both are needed by L3FS.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from oaknut.adfs import ADFS
from oaknut.afs.map_sector import MAGIC
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise
from oaknut.dfs import DFS, DFSPath
from oaknut.file import Access, BootOption

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FS_BINARY = REPO_ROOT / "tests" / "data" / "images" / "cookbook" / "FS3v126.ssd"

# Bitmap-fragmentation stride: how many free sectors between each
# allocated marker within an AFS cylinder. A SCSI hard disc cylinder
# is typically 132 sectors (33 sectors-per-track × 4 heads); marking
# every fourth sector splits the cylinder into ~30 short runs of
# three sectors each. That is well below the 48-extent threshold per
# map block, so the allocator has no choice but to chain into a
# successor block once enough sectors are required.
_FRAGMENTATION_STRIDE = 4


def _copy_fs_binary_to_adfs(adfs: ADFS, dfs_ssd_filepath: Path) -> None:
    """Pull ``$.FS3v126`` off the source SSD and write it to ADFS root.

    Preserves the DFS file's load/exec addresses so the binary is
    runnable; sets the access bits to ``LR/R`` (locked, readable).
    """
    with DFS.from_file(dfs_ssd_filepath) as dfs:
        binary_path = DFSPath(dfs, "$.FS3v126")
        binary_bytes = binary_path.read_bytes()
        binary_stat = binary_path.stat()
    target = adfs.root / "FS3v126"
    target.write_bytes(
        binary_bytes,
        load_address=binary_stat.load_address,
        exec_address=binary_stat.exec_address,
        access=Access.R | Access.W | Access.L,
    )


def _write_boot_file(adfs: ADFS) -> None:
    """Install the ``!BOOT`` command file and set the boot option to EXEC."""
    boot_filepath = adfs.root / "!BOOT"
    boot_filepath.write_bytes(b"*RUN $.FS3v126\r")
    adfs.boot_option = BootOption.EXEC


def _fragment_afs_bitmap(afs) -> None:
    """Pre-fragment the AFS partition's per-cylinder bitmaps.

    Marks every ``_FRAGMENTATION_STRIDE``-th sector of every cylinder
    as allocated, leaving a swiss-cheese pattern. This forces the
    next big allocation to split across many short runs, producing
    more than 48 coalesced data extents — enough to overflow into a
    successor map block.

    Each cylinder's sector 0 is the bitmap itself and is already
    allocated, so we start from offset ``_FRAGMENTATION_STRIDE``.
    """
    shadow = afs._bitmap_shadow()
    sectors_per_cylinder = afs._info.sectors_per_cylinder
    for cyl_index in range(shadow.num_cylinders):
        for sector in range(_FRAGMENTATION_STRIDE, sectors_per_cylinder, _FRAGMENTATION_STRIDE):
            shadow.mark_allocated(cyl_index, sector)
    shadow.flush()


def _write_fragmented_file(afs, payload_sectors: int) -> bytes:
    """Write ``$.Frag`` with a recognisable byte pattern.

    Byte ``i`` of the payload is ``i & 0xFF`` — a 256-byte sawtooth
    repeated across the whole file — so a quick visual scan in a hex
    viewer can spot the wrap points.
    """
    payload = bytes(i & 0xFF for i in range(payload_sectors * 256))
    (afs.root / "Frag").write_bytes(
        payload,
        load_address=0x00FFFF00,
        exec_address=0x00FFFF00,
        access=Access.R | Access.W,
    )
    afs.flush()
    return payload


def _report(afs, payload: bytes) -> tuple[int, list[int]]:
    """Inspect the file we just wrote, print a summary, and return the
    chain shape.

    Returns:
        ``(n_blocks, successor_sins)`` — the total number of map blocks
        in the chain and the SINs of every successor block (i.e. every
        block except the head).
    """
    _, entry = afs._resolve(afs.root / "Frag")
    chain = afs._read_map_chain(entry.sin)
    head_block = chain.blocks[0]
    successor_blocks = chain.blocks[1:]

    print(f"Disc:                {afs.disc_name!r}")
    print(f"$.Frag size:         {len(payload):,} bytes "
          f"({len(payload) // 256} sectors)")
    print(f"$.Frag head SIN:     {int(entry.sin):#x}")
    print(f"$.Frag map blocks:   {len(chain.blocks)}")
    print(f"$.Frag total extents: {sum(len(b.extents) for b in chain.blocks)}")

    head_raw = afs._read_sector(int(head_block.sin))
    print(f"  block 0 (head)  sin={int(head_block.sin):#x}  "
          f"extents={len(head_block.extents)}  "
          f"bytes[0:6]={bytes(head_raw[0:6])!r}")
    for i, block in enumerate(successor_blocks, start=1):
        raw = afs._read_sector(int(block.sin))
        print(f"  block {i} (link)  sin={int(block.sin):#x}  "
              f"extents={len(block.extents)}  "
              f"bytes[0:6]={bytes(raw[0:6])!r}")

    return len(chain.blocks), [int(b.sin) for b in successor_blocks]


def build_fragmented_disc(
    output_filepath: Path,
    *,
    fs_binary_filepath: Path,
    capacity: str = "5MB",
    payload_sectors: int = 400,
    disc_name: str = "FragTest",
) -> None:
    """End-to-end: build a bootable L3FS disc image with chained maps.

    Args:
        output_filepath: Destination ``.dat`` (the companion ``.dsc``
            is written alongside automatically).
        fs_binary_filepath: SSD image containing ``$.FS3v126`` —
            usually the cookbook's ``tests/data/images/cookbook/
            FS3v126.ssd``.
        capacity: ADFS envelope size. ``5MB`` leaves enough room for
            both the FS binary and a small AFS region.
        payload_sectors: Size of the fragmented test file in 256-byte
            sectors. The default of 400 sectors (100 KiB) is well
            above the 48-extent threshold for the fragmentation
            pattern in use.
        disc_name: AFS info-sector disc name.
    """
    if not fs_binary_filepath.exists():
        sys.exit(f"FS binary not found: {fs_binary_filepath}")

    with ADFS.create_file(
        output_filepath,
        capacity=capacity,
        title=disc_name,
    ) as adfs:
        _copy_fs_binary_to_adfs(adfs, fs_binary_filepath)
        _write_boot_file(adfs)

        initialise(
            adfs,
            spec=InitSpec(
                disc_name=disc_name,
                size=AFSSizeSpec.existing_free(),
                users=[UserSpec("RJS", quota="1MB")],
                omit_builtins=frozenset({"Welcome"}),
                libraries=[],
            ),
        )

        afs = adfs.afs_partition
        _fragment_afs_bitmap(afs)
        payload = _write_fragmented_file(afs, payload_sectors)

        n_blocks, successor_sins = _report(afs, payload)

    if n_blocks < 2:
        sys.exit(
            f"FAILED: file fits in {n_blocks} block(s); "
            f"need >1 to exercise the chain. "
            f"Try increasing --payload-sectors."
        )

    # Re-open the image fresh to confirm the parse path tolerates
    # successor blocks with zeros at 0..5 (the bug we just fixed).
    with ADFS.from_file(output_filepath) as adfs:
        afs = adfs.afs_partition
        readback = (afs.root / "Frag").read_bytes()
    if readback != payload:
        sys.exit("FAILED: reopened file content does not match payload.")

    # Confirm the on-disc shape once more from the reopened image:
    # head magic present, every successor's 0..5 still zero.
    with ADFS.from_file(output_filepath) as adfs:
        afs = adfs.afs_partition
        _, entry = afs._resolve(afs.root / "Frag")
        chain = afs._read_map_chain(entry.sin)
        head_raw = afs._read_sector(int(chain.blocks[0].sin))
        if head_raw[0:6] != MAGIC:
            sys.exit(
                f"FAILED: head block missing 'JesMap' magic; got {head_raw[0:6]!r}"
            )
        for block in chain.blocks[1:]:
            raw = afs._read_sector(int(block.sin))
            if raw[0:6] != b"\x00" * 6:
                sys.exit(
                    f"FAILED: successor block sin={int(block.sin):#x} "
                    f"has non-zero bytes at 0..5: {raw[0:6]!r}. "
                    f"That would mean the writer is still writing magic "
                    f"on successors."
                )

    print()
    print(f"Wrote: {output_filepath}")
    print(f"       {output_filepath.with_suffix('.dsc')}")
    print(f"Chain: {n_blocks} map blocks "
          f"({n_blocks - 1} successor(s) with zero magic)")
    print(
        "Boot:  on a real BBC with the L3FS ROM attached, this disc "
        "boots straight into the file server. Logging in and reading "
        "$.Frag should return the sawtooth payload byte-for-byte if "
        "the ROM's chain-walk really does ignore the successor magic."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("fragmented.dat"),
        help="Output .dat path (default: fragmented.dat in cwd).",
    )
    parser.add_argument(
        "--fs-binary",
        type=Path,
        default=DEFAULT_FS_BINARY,
        help=(
            "SSD image containing $.FS3v126 "
            f"(default: {DEFAULT_FS_BINARY.relative_to(REPO_ROOT)})."
        ),
    )
    parser.add_argument(
        "--capacity",
        default="5MB",
        help="ADFS hard-disc capacity (default: 5MB).",
    )
    parser.add_argument(
        "--payload-sectors",
        type=int,
        default=400,
        help=(
            "Size of the fragmented test file, in 256-byte sectors "
            "(default: 400 = 100 KiB)."
        ),
    )
    parser.add_argument(
        "--disc-name",
        default="FragTest",
        help="AFS disc name (default: FragTest).",
    )
    args = parser.parse_args()

    build_fragmented_disc(
        args.output.resolve(),
        fs_binary_filepath=args.fs_binary.resolve(),
        capacity=args.capacity,
        payload_sectors=args.payload_sectors,
        disc_name=args.disc_name,
    )


if __name__ == "__main__":
    main()
