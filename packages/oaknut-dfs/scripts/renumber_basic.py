#!/usr/bin/env -S uv run --quiet --script
# /// script
# requires-python = ">=3.10"
# ///
"""Renumber BBC BASIC program lines in increments of 10.

This script renumbers all line numbers in a BBC BASIC program while
preserving GOTO references. It looks for a sentinel comment to identify
the error handler line for ON ERROR GOTO statements.

Usage:
    uv run scripts/renumber_basic.py input.bas [output.bas]
    # Or directly:
    scripts/renumber_basic.py input.bas [output.bas]

If output.bas is not specified, overwrites input.bas.
"""

import re
import sys
from pathlib import Path


def renumber_basic(input_filepath: Path, output_filepath: Path = None):
    """Renumber BBC BASIC file lines in increments of 10.

    Args:
        input_filepath: Path to input .bas file
        output_filepath: Path to output .bas file (defaults to overwriting input)
    """
    if output_filepath is None:
        output_filepath = input_filepath

    # Read all lines
    with open(input_filepath, 'r') as f:
        lines = f.readlines()

    # Strip any existing line numbers and store the content
    content_lines = []
    for line in lines:
        # Remove line number if present (number followed by space or colon)
        stripped = re.sub(r'^\d+[ \t:]?', '', line)
        content_lines.append(stripped)

    # Find error handler line for later
    error_handler_line_index = None
    for i, line in enumerate(content_lines):
        if 'REM Error handler' in line or 'REM error handler' in line:
            error_handler_line_index = i
            break

    # Renumber all non-blank lines
    new_line_num = 10
    old_to_new = {}  # For updating GOTO references
    renumbered_lines = []

    for i, content in enumerate(content_lines):
        # Check if line is blank
        if content.strip() == '':
            # Blank line becomes numbered colon
            renumbered_lines.append(f"{new_line_num} :\n")
            new_line_num += 10
        elif re.match(r'^[ \t]*:\s*$', content):
            # Line is just a colon - renumber it
            renumbered_lines.append(f"{new_line_num} :\n")
            new_line_num += 10
        else:
            # Regular line - add line number
            renumbered_lines.append(f"{new_line_num} {content}")
            new_line_num += 10

    # Update ON ERROR GOTO statements if we found an error handler
    if error_handler_line_index is not None:
        error_handler_new_line = (error_handler_line_index + 1) * 10
        for i, line in enumerate(renumbered_lines):
            if 'ON ERROR' in line and 'GOTO' in line:
                # Replace any GOTO target in ON ERROR line with error handler line
                renumbered_lines[i] = re.sub(
                    r'GOTO \d+',
                    f'GOTO {error_handler_new_line}',
                    line
                )

    # Write output
    with open(output_filepath, 'w') as f:
        f.writelines(renumbered_lines)

    print(f"Renumbered {len([l for l in renumbered_lines if l.strip()])} lines")
    if error_handler_line_index is not None:
        error_handler_new_line = (error_handler_line_index + 1) * 10
        print(f"Error handler at line {error_handler_new_line}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_filepath = Path(sys.argv[1])
    output_filepath = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    if not input_filepath.exists():
        print(f"Error: {input_filepath} does not exist")
        sys.exit(1)

    renumber_basic(input_filepath, output_filepath)
    print(f"Successfully renumbered {input_filepath}")


if __name__ == '__main__':
    main()
