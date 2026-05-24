"""Archive a folder of DFS ``.ssd`` floppies onto one ADFS hard disc.

Python counterpart to the bulk-archive CLI recipe. The shape is the
same — for each SSD on the host, create a like-named subdirectory on
the archive disc and copy every file across — but using the Python
API lets a script integrate naming, filtering, or progress reporting
inline rather than via shell.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

from oaknut.adfs import ADFS
from oaknut.dfs import DFS


_LEADING_PASCAL_WORD = re.compile(r".*-([A-Z][a-z]+)")


def archive_floppies(ssd_filepaths: list[Path], archive_filepath: Path) -> None:
    """Copy every file from each SSD into its own ADFS subdirectory.

    The subdirectory name comes from the first PascalCase word in the
    SSD filename — ``Disc001-PlanetoidAKADefender.ssd`` becomes
    ``Planetoid``, well within ADFS's 10-character filename limit.
    """
    with ADFS.from_file(archive_filepath, mode="r+b") as archive:
        for ssd in ssd_filepaths:
            name = _subdir_name_for(ssd)
            subdir = archive.root / name
            subdir.mkdir()
            with DFS.from_file(ssd) as floppy:
                for letter in floppy.root.iterdir():
                    for entry in letter.iterdir():
                        entry.copy_to(subdir / entry.name)


def _subdir_name_for(ssd_filepath: Path) -> str:
    match = _LEADING_PASCAL_WORD.match(ssd_filepath.stem)
    if match is None:
        return ssd_filepath.stem[:10]
    return match.group(1)


def _build_three_floppies(workdir: Path) -> list[Path]:
    """Synthesise three DFS floppies so the recipe has something to archive."""
    floppies = []
    for stem, title, files in [
        ("Disc001-PlanetoidAKADefender", "PLANET", [("PLANET", b"\x00" * 100)]),
        ("Disc002-Arcadians", "ARC", [("ARC", b"\x00" * 50), ("ARCDAT", b"x" * 32)]),
        ("Disc003-Zalaga", "ZALAG", [("ZALAG", b"\x00" * 64)]),
    ]:
        ssd = workdir / f"{stem}.ssd"
        with DFS.create_file(ssd, title=title) as dfs:
            for name, data in files:
                (dfs.root / f"$.{name}").write_bytes(data, load_address=0x1900)
        floppies.append(ssd)
    return floppies


def main(workdir: Path) -> None:
    sources = _build_three_floppies(workdir)
    archive = workdir / "games.dat"
    with ADFS.create_file(archive, capacity="10MB", title="Games"):
        pass
    archive_floppies(sources, archive)

    with ADFS.from_file(archive) as adfs:
        for sub in sorted(adfs.root.iterdir(), key=lambda p: p.name):
            kids = sorted(p.name for p in sub.iterdir())
            print(f"  {sub.name}/  {kids}")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        main(Path(tmp))
