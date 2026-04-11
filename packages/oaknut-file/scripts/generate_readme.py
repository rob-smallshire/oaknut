#!/usr/bin/env python3
"""Generate README.md by executing oaknut-file API snippets and rendering a Jinja2 template.

Ensures that all code examples in the README are up-to-date with the
actual behaviour of the oaknut-file package.

Usage:
    ./scripts/generate_readme.py              # write to README.md
    ./scripts/generate_readme.py --check      # check README.md is up-to-date
"""

from __future__ import annotations

import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_DIRPATH = Path(__file__).resolve().parent.parent
TEMPLATE_DIRPATH = REPO_DIRPATH / "scripts"
TEMPLATE_FILENAME = "README.md.j2"
OUTPUT_FILEPATH = REPO_DIRPATH / "README.md"


def collect_examples() -> dict[str, str]:
    """Run real API examples and capture their output."""
    from oaknut_file import (
        Access,
        AcornMeta,
        format_pieb_inf_line,
        format_trad_inf_line,
        parse_encoded_filename,
        parse_inf_line,
    )

    # Access flag composition
    access_example = repr(Access.R | Access.W | Access.L)
    access_int = f"0x{int(Access.R | Access.W | Access.L):02X}"

    # Traditional INF line
    trad_line = format_trad_inf_line(
        filename="HELLO",
        load_addr=0x1900,
        exec_addr=0x8023,
        length=0x100,
        attr=int(Access.R | Access.W),
    )

    # PiEconetBridge INF line
    pieb_line = format_pieb_inf_line(
        load_addr=0xFFFFDD00,
        exec_addr=0xFFFFDD00,
        attr=int(Access.R | Access.W | Access.L | Access.PR),
    )

    # Parse INF (auto-detect format)
    _, trad_meta = parse_inf_line(trad_line)
    trad_parsed = (
        f"load_addr=0x{trad_meta.load_addr:X}, "
        f"exec_addr=0x{trad_meta.exec_addr:X}, "
        f"attr=0x{trad_meta.attr:02X}"
    )

    _, pieb_meta = parse_inf_line(pieb_line)
    pieb_parsed = (
        f"load_addr=0x{pieb_meta.load_addr:X}, "
        f"exec_addr=0x{pieb_meta.exec_addr:X}, "
        f"attr=0x{pieb_meta.attr:02X}, "
        f"filetype=0x{pieb_meta.filetype:03X}"
    )

    # Filename encoding
    clean, fn_meta = parse_encoded_filename("PROG,ffb")
    filename_parsed = f"({clean!r}, filetype=0x{fn_meta.infer_filetype():03X})"

    clean2, fn_meta2 = parse_encoded_filename("PROG,1900-801f")
    mos_parsed = (
        f"({clean2!r}, "
        f"load_addr=0x{fn_meta2.load_addr:X}, "
        f"exec_addr=0x{fn_meta2.exec_addr:X})"
    )

    # Filetype detection from a load address
    riscos_meta = AcornMeta(load_addr=0xFFFF0E10)
    filetype_demo = (
        f"is_filetype_stamped={riscos_meta.is_filetype_stamped}, "
        f"infer_filetype()=0x{riscos_meta.infer_filetype():03X}"
    )

    return {
        "access_example": access_example,
        "access_int": access_int,
        "trad_line": trad_line,
        "pieb_line": pieb_line,
        "trad_parsed": trad_parsed,
        "pieb_parsed": pieb_parsed,
        "filename_parsed": filename_parsed,
        "mos_parsed": mos_parsed,
        "filetype_demo": filetype_demo,
    }


def generate() -> str:
    """Render the README template with live examples."""
    examples = collect_examples()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIRPATH)),
        keep_trailing_newline=True,
    )
    template = env.get_template(TEMPLATE_FILENAME)
    return template.render(**examples)


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
