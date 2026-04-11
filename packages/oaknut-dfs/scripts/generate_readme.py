"""Generate README.md by running oaknut-dfs API operations and rendering a Jinja2 template.

Ensures that all code examples in the README are up-to-date with the actual
behaviour of the oaknut-dfs library.

Usage:
    ./scripts/generate_readme.py              # write to README.md
    ./scripts/generate_readme.py --check      # check README.md is up-to-date
"""

from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Register catalogue classes before using DFS
import oaknut_dfs.acorn_dfs_catalogue  # noqa: F401

from oaknut_dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED

REPO_DIRPATH = Path(__file__).resolve().parent.parent
TEMPLATE_DIRPATH = REPO_DIRPATH / "scripts"
TEMPLATE_FILENAME = "README.md.j2"
OUTPUT_FILEPATH = REPO_DIRPATH / "README.md"
FIXTURE_FILEPATH = REPO_DIRPATH / "tests" / "data" / "images" / "games" / "Disc003-Zalaga.ssd"
ADFS_FIXTURE_FILEPATH = REPO_DIRPATH / "tests" / "images" / "MasterWelcome.adl"


def _load_game_disc() -> DFS:
    """Load the Zalaga game disc for README examples."""
    buffer = bytearray(FIXTURE_FILEPATH.read_bytes())
    return DFS.from_buffer(memoryview(buffer), ACORN_DFS_80T_SINGLE_SIDED)


# --- DFS examples ---


def capture_dfs_open() -> str:
    dfs = _load_game_disc()
    title = dfs.title.rstrip("\x00")
    lines = [
        "from oaknut_dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED",
        "",
        'with DFS.from_file("Zalaga.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:',
        f"    print(dfs.title)   # {title!r}",
        "",
        "    # Navigate with pathlib-inspired API",
        '    for entry in dfs.root / "$":',
        "        s = entry.stat()",
        '        print(f"{entry.name:10s}  {s.length:6d}  load={s.load_address:08X}")',
        "",
        "    # Read file data",
        '    data = (dfs.root / "$" / "ZALAGA").read_bytes()',
    ]
    return "\n".join(lines)


def capture_dfs_create() -> str:
    lines = [
        "from oaknut_dfs import DFS, ACORN_DFS_80T_SINGLE_SIDED",
        "",
        'with DFS.create_file("demo.ssd", ACORN_DFS_80T_SINGLE_SIDED, title="DEMO") as dfs:',
        '    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1900)',
        '    dfs.save("$.README", b"oaknut-dfs demo disc")',
    ]
    return "\n".join(lines)


def capture_dfs_dsd() -> str:
    lines = [
        "from oaknut_dfs import DFS, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED",
        "",
        'with DFS.from_file("game.dsd", ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED) as side0:',
        "    print(side0.title)",
        "",
        'with DFS.from_file("game.dsd", ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, side=1) as side1:',
        "    print(side1.title)",
    ]
    return "\n".join(lines)


def capture_dfs_walk() -> str:
    lines = [
        'with DFS.from_file("disc.ssd", ACORN_DFS_80T_SINGLE_SIDED) as dfs:',
        "    for dirpath, dirnames, filenames in dfs.root.walk():",
        "        for name in filenames:",
        "            print(dirpath / name)",
    ]
    return "\n".join(lines)


# --- ADFS floppy examples ---


def capture_adfs_floppy_open() -> str:
    lines = [
        "from oaknut_dfs import ADFS",
        "",
        'with ADFS.from_file("MasterWelcome.adl") as adfs:',
    ]

    from oaknut_dfs import ADFS
    if ADFS_FIXTURE_FILEPATH.exists():
        with ADFS.from_file(ADFS_FIXTURE_FILEPATH) as adfs:
            lines.append(f'    print(adfs.title)   # {adfs.title!r}')
    else:
        lines.append("    print(adfs.title)   # '80T Welcome & Utils'")

    lines.extend([
        "",
        "    # Navigate with / operator",
        '    for entry in adfs.root / "LIBRARY":',
        "        print(entry.name, entry.stat().length)",
        "",
        "    # Read a file",
        '    data = (adfs.root / "HELP" / "aform").read_bytes()',
    ])
    return "\n".join(lines)


def capture_adfs_floppy_walk() -> str:
    lines = [
        'with ADFS.from_file("disc.adl") as adfs:',
        "    for dirpath, dirnames, filenames in adfs.root.walk():",
        "        for name in filenames:",
        "            print(dirpath / name)",
    ]
    return "\n".join(lines)


def capture_adfs_floppy_create() -> str:
    lines = [
        "from oaknut_dfs import ADFS, ADFS_L",
        "",
        'with ADFS.create_file("blank.adl", ADFS_L, title="My Disc") as adfs:',
        "    pass  # empty formatted disc ready for use",
    ]
    return "\n".join(lines)


# --- ADFS hard disc examples ---


def capture_adfs_hdd_open() -> str:
    lines = [
        "from oaknut_dfs import ADFS",
        "",
        'with ADFS.from_file("scsi0.dat") as adfs:',
        "    print(adfs.title)",
        '    print(f"{adfs.total_size // 1024}KB, {adfs.free_space // 1024}KB free")',
        "",
        "    for dirpath, dirnames, filenames in adfs.root.walk():",
        "        for name in filenames:",
        "            p = dirpath / name",
        '            print(f"{p}  {p.stat().length}")',
    ]
    return "\n".join(lines)


def capture_adfs_hdd_create() -> str:
    lines = [
        "from oaknut_dfs import ADFS",
        "",
        "# Create a 20MB hard disc image",
        'with ADFS.create_file("scsi0.dat", capacity_bytes=20 * 1024 * 1024, title="Data") as adfs:',
        "    pass  # creates both scsi0.dat and scsi0.dsc",
    ]
    return "\n".join(lines)


def capture_adfs_hdd_create_explicit() -> str:
    lines = [
        'with ADFS.create_file("scsi0.dat", cylinders=306, heads=4) as adfs:',
        "    pass",
    ]
    return "\n".join(lines)


# --- Main ---


def generate() -> str:
    """Run all demonstrations and render the README template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIRPATH)),
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_FILENAME)

    return template.render(
        dfs_open=capture_dfs_open(),
        dfs_create=capture_dfs_create(),
        dfs_dsd=capture_dfs_dsd(),
        dfs_walk=capture_dfs_walk(),
        adfs_floppy_open=capture_adfs_floppy_open(),
        adfs_floppy_walk=capture_adfs_floppy_walk(),
        adfs_floppy_create=capture_adfs_floppy_create(),
        adfs_hdd_open=capture_adfs_hdd_open(),
        adfs_hdd_create=capture_adfs_hdd_create(),
        adfs_hdd_create_explicit=capture_adfs_hdd_create_explicit(),
    )


def main() -> int:
    check_mode = "--check" in sys.argv

    rendered = generate()

    if check_mode:
        if not OUTPUT_FILEPATH.is_file():
            print(f"ERROR: {OUTPUT_FILEPATH} does not exist", file=sys.stderr)
            return 1
        current = OUTPUT_FILEPATH.read_text()
        if current == rendered:
            print("README.md is up-to-date.")
            return 0
        else:
            print(
                "ERROR: README.md is out of date. "
                "Regenerate with: uv run --group dev scripts/generate_readme.py",
                file=sys.stderr,
            )
            return 1

    OUTPUT_FILEPATH.write_text(rendered)
    print(f"Wrote {OUTPUT_FILEPATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
