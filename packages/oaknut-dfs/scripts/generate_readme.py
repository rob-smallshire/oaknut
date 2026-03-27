"""Generate README.md by running oaknut-dfs API operations and rendering a Jinja2 template.

Ensures that all code examples in the README are up-to-date with the actual
behaviour of the oaknut-dfs library.

Usage:
    ./scripts/generate_readme.py              # write to README.md
    ./scripts/generate_readme.py --check      # check README.md is up-to-date
"""

from __future__ import annotations

import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

# Register catalogue classes before using DFS
import oaknut_dfs.acorn_dfs_catalogue  # noqa: F401

from oaknut_dfs import DFS
from oaknut_dfs.formats import (
    ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED,
    ACORN_DFS_40T_SINGLE_SIDED,
)

REPO_DIRPATH = Path(__file__).resolve().parent.parent
TEMPLATE_DIRPATH = REPO_DIRPATH / "scripts"
TEMPLATE_FILENAME = "README.md.j2"
OUTPUT_FILEPATH = REPO_DIRPATH / "README.md"


def _create_empty_ssd(title: str = "", total_sectors: int = 400) -> bytearray:
    """Create a minimal 40-track SSD buffer with a valid empty catalogue."""
    buffer = bytearray(total_sectors * 256)
    # Title: first 8 bytes in sector 0, next 4 bytes in sector 1
    encoded_title = title.encode("acorn")[:12].ljust(12, b" ")
    buffer[0:8] = encoded_title[:8]
    buffer[256:260] = encoded_title[8:12]
    # Number of files * 8 in sector 1 byte 5
    buffer[261] = 0
    # Total sectors: high bits in byte 6 (bits 0-1), low byte in byte 7
    buffer[262] = (total_sectors >> 8) & 0x03
    buffer[263] = total_sectors & 0xFF
    return buffer


def _create_empty_dsd(
    title_side0: str = "", title_side1: str = "", total_sectors_per_side: int = 400
) -> bytearray:
    """Create a minimal 40-track interleaved DSD buffer with valid catalogues on both sides."""
    # Interleaved DSD: tracks alternate sides (track 0 side 0, track 0 side 1, track 1 side 0, ...)
    num_tracks = total_sectors_per_side // 10
    buffer = bytearray(num_tracks * 2 * 10 * 256)

    # Side 0 catalogue is at the start (track 0, side 0)
    encoded_title0 = title_side0.encode("acorn")[:12].ljust(12, b" ")
    buffer[0:8] = encoded_title0[:8]
    buffer[256:260] = encoded_title0[8:12]
    buffer[261] = 0
    buffer[262] = (total_sectors_per_side >> 8) & 0x03
    buffer[263] = total_sectors_per_side & 0xFF

    # Side 1 catalogue starts at offset 2560 (track 0, side 1)
    side1_offset = 2560
    encoded_title1 = title_side1.encode("acorn")[:12].ljust(12, b" ")
    buffer[side1_offset : side1_offset + 8] = encoded_title1[:8]
    buffer[side1_offset + 256 : side1_offset + 260] = encoded_title1[8:12]
    buffer[side1_offset + 261] = 0
    buffer[side1_offset + 262] = (total_sectors_per_side >> 8) & 0x03
    buffer[side1_offset + 263] = total_sectors_per_side & 0xFF

    return buffer


def _capture(func) -> str:
    """Capture stdout from a function call."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        func()
    return buf.getvalue().rstrip()


def capture_basic_usage() -> str:
    """Demonstrate creating a DFS instance and inspecting it."""
    buf = _create_empty_ssd("DEMO")
    dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)

    lines = [
        "from oaknut_dfs import DFS, ACORN_DFS_40T_SINGLE_SIDED",
        "",
        "# Create a 40-track single-sided disc image (102,400 bytes)",
        "buffer = bytearray(102400)",
        "# ... initialise catalogue sectors ...",
        "",
        "dfs = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_SINGLE_SIDED)",
        f"print(dfs.title)   # {dfs.title!r}",
        f"print(repr(dfs))   # {dfs!r}",
    ]
    return "\n".join(lines)


def capture_save_load() -> str:
    """Demonstrate saving and loading files."""
    buf = _create_empty_ssd("DEMO")
    dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)

    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)
    dfs.save("$.README", b"oaknut-dfs demo disc", load_address=0x0000, exec_address=0x0000)

    loaded = dfs.load("$.HELLO")

    lines = [
        "# Save files with load and execution addresses",
        'dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)',
        'dfs.save("$.README", b"oaknut-dfs demo disc")',
        "",
        "# Load a file back",
        'data = dfs.load("$.HELLO")',
        f"print(data)   # {loaded!r}",
    ]
    return "\n".join(lines)


def capture_file_listing() -> str:
    """Demonstrate listing files."""
    buf = _create_empty_ssd("DEMO")
    dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)

    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)
    dfs.save("$.README", b"oaknut-dfs demo disc", load_address=0x0000, exec_address=0x0000)
    dfs.save("$.PROG", b"\x00" * 512, load_address=0x3000, exec_address=0x3000, locked=True)

    lines = [
        "for entry in dfs.files:",
        '    lock = "L" if entry.locked else " "',
        '    print(f"{lock} {entry.path:10s}  {entry.load_address:06X}  '
        '{entry.exec_address:06X}  {entry.length:06X}")',
    ]

    for entry in dfs.files:
        lock = "L" if entry.locked else " "
        lines.append(
            f"# {lock} {entry.path:10s}  {entry.load_address:06X}  "
            f"{entry.exec_address:06X}  {entry.length:06X}"
        )

    return "\n".join(lines)


def capture_file_info() -> str:
    """Demonstrate get_file_info()."""
    buf = _create_empty_ssd("DEMO")
    dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)

    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)

    info = dfs.get_file_info("$.HELLO")

    lines = [
        'info = dfs.get_file_info("$.HELLO")',
        f"print(info.name)            # {info.name!r}",
        f"print(hex(info.load_address))  # {hex(info.load_address)}",
        f"print(hex(info.exec_address))  # {hex(info.exec_address)}",
        f"print(info.length)          # {info.length}",
        f"print(info.locked)          # {info.locked}",
        f"print(info.start_sector)    # {info.start_sector}",
        f"print(info.sectors)         # {info.sectors}",
    ]
    return "\n".join(lines)


def capture_disc_info() -> str:
    """Demonstrate the .info property."""
    buf = _create_empty_ssd("DEMO")
    dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)

    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)

    info = dfs.info

    lines = [
        "print(dfs.info)",
    ]
    # Format the dict nicely
    formatted_items = [f"    {k!r}: {v!r}," for k, v in info.items()]
    lines.append("# {")
    for item in formatted_items:
        lines.append(f"# {item}")
    lines.append("# }")

    return "\n".join(lines)


def capture_pythonic() -> str:
    """Demonstrate Pythonic interface."""
    buf = _create_empty_ssd("DEMO")
    dfs = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_SINGLE_SIDED)

    dfs.save("$.HELLO", b"Hello, World!", load_address=0x1200, exec_address=0x1200)
    dfs.save("$.README", b"oaknut-dfs demo disc", load_address=0x0000, exec_address=0x0000)

    lines = [
        "# Check if a file exists",
        f'print("$.HELLO" in dfs)   # {"$.HELLO" in dfs}',
        f'print("$.NOPE" in dfs)    # {"$.NOPE" in dfs}',
        "",
        "# Number of files",
        f"print(len(dfs))            # {len(dfs)}",
        "",
        "# Iterate over files",
        "for entry in dfs:",
        "    print(entry.path)",
    ]

    for entry in dfs:
        lines.append(f"# {entry.path}")

    return "\n".join(lines)


def capture_dsd_example() -> str:
    """Demonstrate double-sided disc access."""
    buf = _create_empty_dsd("SIDE ZERO", "SIDE ONE")
    dfs0 = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=0)
    dfs1 = DFS.from_buffer(memoryview(buf), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=1)

    dfs0.save("$.FILE0", b"side 0 data", load_address=0x1200, exec_address=0x1200)
    dfs1.save("$.FILE1", b"side 1 data", load_address=0x3000, exec_address=0x3000)

    lines = [
        "from oaknut_dfs import ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED",
        "",
        "# DSD images contain two independent sides, each with its own catalogue.",
        "# This mirrors the BBC Micro, where double-sided discs were accessed as",
        "# separate drives using *DRIVE 0 and *DRIVE 2.",
        "",
        "buffer = bytearray(204800)  # 40-track double-sided",
        "# ... initialise catalogue sectors for both sides ...",
        "",
        "# Access each side independently",
        "dfs0 = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=0)",
        "dfs1 = DFS.from_buffer(memoryview(buffer), ACORN_DFS_40T_DOUBLE_SIDED_INTERLEAVED, side=1)",
        "",
        "# Each side has its own title, files, and catalogue",
        f'print(dfs0.title)   # {dfs0.title!r}',
        f'print(dfs1.title)   # {dfs1.title!r}',
        "",
        '# Files on one side are not visible from the other',
        f'print("$.FILE0" in dfs0)   # {"$.FILE0" in dfs0}',
        f'print("$.FILE0" in dfs1)   # {"$.FILE0" in dfs1}',
    ]
    return "\n".join(lines)


def generate() -> str:
    """Run all demonstrations and render the README template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIRPATH)),
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_FILENAME)

    return template.render(
        basic_usage=capture_basic_usage(),
        save_load=capture_save_load(),
        file_listing=capture_file_listing(),
        file_info=capture_file_info(),
        disc_info=capture_disc_info(),
        pythonic=capture_pythonic(),
        dsd_example=capture_dsd_example(),
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
                "Regenerate with: uv run scripts/generate_readme.py",
                file=sys.stderr,
            )
            return 1

    OUTPUT_FILEPATH.write_text(rendered)
    print(f"Wrote {OUTPUT_FILEPATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
