"""Human-friendly byte-capacity parser.

Parses strings like ``"10MB"``, ``"40MiB"``, ``"1024kB"``, or plain
``"10485760"`` into integer byte counts.

Suffixes are case-insensitive:

====== ============ ==========
Suffix  Meaning     Multiplier
====== ============ ==========
(none) bytes        1
B      bytes        1
kB     kilobytes    1,000
KiB    kibibytes    1,024
MB     megabytes    1,000,000
MiB    mebibytes    1,048,576
GB     gigabytes    1,000,000,000
GiB    gibibytes    1,073,741,824
====== ============ ==========

A space between the number and the suffix is permitted.
"""

from __future__ import annotations

import re

_SUFFIX_MULTIPLIERS: dict[str, int] = {
    "b": 1,
    "kb": 1_000,
    "kib": 1_024,
    "mb": 1_000_000,
    "mib": 1_024 * 1_024,
    "gb": 1_000_000_000,
    "gib": 1_024 * 1_024 * 1_024,
}

_CAPACITY_RE = re.compile(
    r"^\s*(\d+)\s*([a-zA-Z]*)\s*$",
)


def parse_capacity(text: str) -> int:
    """Parse a human-friendly capacity string into bytes.

    Raises :class:`ValueError` on unrecognised input.
    """
    m = _CAPACITY_RE.match(text)
    if m is None:
        raise ValueError(f"cannot parse capacity: {text!r}")

    number = int(m.group(1))
    suffix = m.group(2).lower()

    if not suffix:
        # Bare number — implicit bytes.
        result = number
    elif suffix in _SUFFIX_MULTIPLIERS:
        result = number * _SUFFIX_MULTIPLIERS[suffix]
    else:
        raise ValueError(
            f"unrecognised capacity suffix '{m.group(2)}' in {text!r}; "
            f"expected B, kB, KiB, MB, MiB, GB, or GiB"
        )

    if result < 0:
        raise ValueError(f"capacity must be non-negative, got {result}")
    return result
