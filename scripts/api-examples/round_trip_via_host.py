"""Round-trip a file through the host filesystem and back.

The symmetric export_file and import_file methods live on every path
class (DFSPath, ADFSPath, AFSPath). Together with one of the metadata
formats they preserve load address, exec address, and access bits
across the host crossing without the caller having to assemble or
disassemble an AcornMeta by hand.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from oaknut.adfs import ADFS, ADFS_L
from oaknut.file import Access, MetaFormat


def round_trip(image_filepath: Path, host_dirpath: Path) -> None:
    """Export every file in the ADFS root, then re-import to a fresh image.

    The pattern reads:

      source.export_file(host_path, meta_format=...) pulls bytes
      and metadata onto the host, dropping an INF sidecar so nothing
      is lost.

      destination.import_file(host_path, meta_formats=[...]) picks
      the sidecar back up at the destination, applying load, exec,
      and access in one call.

    Args:
        image_filepath: Source ADFS image to round-trip.
        host_dirpath: Directory on the host where the intermediate
            file plus INF sidecar are written, and where the fresh
            image is created.
    """
    fresh_filepath = host_dirpath / "round_trip.adl"
    with (
        ADFS.from_file(image_filepath) as source,
        ADFS.create_file(fresh_filepath, ADFS_L, title="RoundTrip") as target,
    ):
        for entry in source.root.iterdir():
            if entry.is_dir():
                continue
            host_path = host_dirpath / entry.name
            entry.export_file(host_path, meta_format=MetaFormat.INF_TRAD)
            (target.root / entry.name).import_file(host_path)

    # Verify the bits actually round-tripped intact.
    with (
        ADFS.from_file(image_filepath) as source,
        ADFS.from_file(fresh_filepath) as target,
    ):
        for entry in source.root.iterdir():
            if entry.is_dir():
                continue
            src_st = entry.stat()
            tgt_st = (target.root / entry.name).stat()
            assert src_st.load_address == tgt_st.load_address
            assert src_st.exec_address == tgt_st.exec_address
            # Access bits that the host metadata format can carry.
            assert bool(src_st.access & Access.L) == bool(tgt_st.access & Access.L)
            assert entry.read_bytes() == (target.root / entry.name).read_bytes()
    print(f"Round-trip OK: {fresh_filepath.name}")


def _build_source_disc(workdir: Path) -> Path:
    """A small ADFS source disc to round-trip from."""
    filepath = workdir / "source.adl"
    with ADFS.create_file(filepath, ADFS_L, title="Source") as adfs:
        (adfs.root / "ReadMe").write_text("Hello!\n", load_address=0xFFFFFD00)
        (adfs.root / "Code").write_bytes(
            b"\xa9\x41\x60",
            load_address=0x1900,
            exec_address=0x1900,
        )
        (adfs.root / "Locked").write_text("static\n", access=Access.LWR)
    return filepath


def main(workdir: Path) -> None:
    source = _build_source_disc(workdir)
    host_dir = workdir / "host"
    host_dir.mkdir()
    round_trip(source, host_dir)


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))
