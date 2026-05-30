"""Build four synthetic Acorn DFS discs of daily temperature telemetry.

One disc per month — January to April 1984 — each holding one file per
day, named ``84MMDD`` (e.g. ``840101`` for 1984-01-01). Each file is the
day's 24 hourly air temperatures for Cambridge, England, in degrees
Celsius, as carriage-return-separated ASCII numbers (the Acorn line
ending).

The point of four discs is capacity: a month has up to 31 days, which is
exactly Acorn DFS's per-disc file limit, so each month fills a disc. The
companion cookbook recipe consolidates all four onto one double-sided
Watford DFS disc, whose 62-files-per-side catalogue swallows two months
a side.

The temperatures are synthetic but plausible — a seasonal baseline that
warms from January to April, a daily wobble (cold snaps and mild
spells), and a diurnal swing coldest before dawn and warmest mid
afternoon. The model is deterministic, so regenerating the discs yields
byte-identical images.

Usage::

    uv run python scripts/build_telemetry_discs.py

Writes ``telem-84MM.ssd`` for MM in 01..04 into
``tests/data/images/telemetry/`` (override with ``--output-dir``).
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import ACORN_DFS_40T_SINGLE_SIDED

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = REPO_ROOT / "tests" / "data" / "images" / "telemetry"

# 1984 is a leap year, so February has 29 days. Each (month, days, title).
MONTHS = [
    (1, 31, "Jan 84 Temps"),
    (2, 29, "Feb 84 Temps"),
    (3, 31, "Mar 84 Temps"),
    (4, 30, "Apr 84 Temps"),
]

# Approximate daily-mean air temperature (deg C) for Cambridge, by month —
# a cold late winter easing into a mild early spring.
_SEASONAL_MEAN = {1: 4.0, 2: 4.5, 3: 6.5, 4: 9.0}


def hourly_temperatures(month: int, day: int) -> list[float]:
    """The 24 hourly temperatures (deg C) for one day, deterministically.

    Seasonal baseline + a day-to-day wobble + a diurnal swing (coldest
    around 05:00, warmest around 15:00). Rounded to one decimal place.
    """
    baseline = _SEASONAL_MEAN[month]
    baseline += (day - 15) * 0.04  # gentle warming through the month
    baseline += 2.2 * math.sin(day * 0.7)  # cold snaps and mild spells
    temps = []
    for hour in range(24):
        diurnal = 3.6 * math.cos((hour - 15) / 24 * 2 * math.pi)
        temps.append(round(baseline + diurnal, 1))
    return temps


def day_file_bytes(month: int, day: int) -> bytes:
    """One day's file: 24 hourly temperatures, CR-separated ASCII."""
    lines = [f"{value:.1f}" for value in hourly_temperatures(month, day)]
    return ("\r".join(lines) + "\r").encode("ascii")


def build_month(output_dirpath: Path, month: int, days: int, title: str) -> Path:
    image_filepath = output_dirpath / f"telem-84{month:02d}.ssd"
    with DFS.create_file(image_filepath, ACORN_DFS_40T_SINGLE_SIDED, title=title) as dfs:
        for day in range(1, days + 1):
            filename = f"84{month:02d}{day:02d}"
            (dfs.root / f"$.{filename}").write_bytes(
                day_file_bytes(month, day), load_address=0x0000, exec_address=0x0000
            )
    return image_filepath


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory to write the .ssd images into.",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for month, days, title in MONTHS:
        image_filepath = build_month(args.output_dir, month, days, title)
        print(f"wrote {image_filepath.relative_to(REPO_ROOT)} — {days} days, title {title!r}")


if __name__ == "__main__":
    main()
