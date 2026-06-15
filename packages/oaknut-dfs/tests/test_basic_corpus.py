"""Round-trip every real BBC BASIC program in the disc-image corpus.

The strongest possible check on the :mod:`oaknut.basic` codec: take
genuine tokenised programs produced by real BBC machines (the ones
shipped inside this repo's DFS and ADFS test images), de-tokenise each to
a listing, re-tokenise it, and require the bytes to come back identical.

This is a cross-cutting test — it needs DFS *and* ADFS to read the images
and ``oaknut.basic`` to round-trip — so it lives with the other
cross-cutting image suites in ``oaknut-dfs``.

Twenty programs are known not to round-trip byte-exactly; they are listed
in :data:`KNOWN_LIMITATIONS` with the reason. Every *other* program found
must round-trip, so a regression in a currently-passing program fails
here even though the known limitations are tolerated.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("oaknut.adfs")
pytest.importorskip("oaknut.basic")

from oaknut.basic import detokenise, tokenise  # noqa: E402

_WORKSPACE_ROOT = Path(__file__).resolve().parents[3]

# Programs that do not round-trip byte-exactly. None is an oaknut.basic
# defect: each is a property of how the particular program was tokenised,
# not of our BASIC II codec (whose crunch is verified vector-for-vector
# against the ROM in oaknut-basic's test_crunch_rules.py). The causes:
#
#   * foreign tokeniser — the program contains keyword tokens *interior*
#     to a name run (e.g. G[DIV]40, =[TRUE][ELSE]=), which BASIC II never
#     produces (a keyword matches only at a run start). These were
#     tokenised by a different BASIC — note most are on MasterWelcome.adl,
#     a BBC Master disc (BASIC IV) — so re-crunching under BASIC II rules
#     correctly yields the literal form.
#   * non-canonical line-number encoding — the &8D codec is many-to-one;
#     these were written (by RENUMBER or a tool) with a non-canonical
#     encoding that decodes correctly but re-encodes to the canonical form.
#   * tokens-after-REM — the program stores keyword tokens after a REM,
#     which the ROM crunch (and ours) never produces from text.
KNOWN_LIMITATIONS: frozenset[str] = frozenset(
    {
        "Disc999-SphinxAdventureFIN.ssd:$.SPHINX",
        "L3-Utils.dsd:U.Init",
        "L3FS-ISW.adl:$.COPYF",
        "L3FS-ISW.adl:$.Utils.CopyFiles",
        "L3FS-ISW.adl:$.Utils.DirCopy",
        "Level_3_FS_Utilities_Disc_v106.dsd:U.Copyf",
        "MasterWelcome.adl:$.ADFS_Tutor",
        "MasterWelcome.adl:$.AdventInfo",
        "MasterWelcome.adl:$.Chardes",
        "MasterWelcome.adl:$.Copyfiles",
        "MasterWelcome.adl:$.DbaseInfo",
        "MasterWelcome.adl:$.Dircopy",
        "MasterWelcome.adl:$.EnvelInfo",
        "MasterWelcome.adl:$.Envelope",
        "MasterWelcome.adl:$.Modes",
        "MasterWelcome.adl:$.Pfill",
        "MasterWelcome.adl:$.TimPaint",
        "MasterWelcome.adl:$.TurtleInfo",
        "l3server.adl:$.CopyF",
        "l3server.adl:$.WFSInit",
    }
)

# The corpus is large enough that a sharp drop signals images failing to
# open (rather than a genuinely empty sweep).
_MIN_PROGRAMS_EXPECTED = 120


def _looks_like_tokenised_basic(data: bytes) -> bool:
    """True for a well-formed program: 0D hi lo len ... records to 0D FF."""
    n = len(data)
    if n < 2 or data[0] != 0x0D:
        return False
    i = 0
    while i < n:
        if data[i] != 0x0D or i + 1 >= n:
            return False
        if data[i + 1] == 0xFF:
            return i + 2 == n
        if i + 4 > n:
            return False
        length = data[i + 3]
        if length < 4 or i + length > n:
            return False
        i += length
    return False


def _walk(path) -> Iterator[tuple[str, bytes]]:
    for entry in path.iterdir():
        if entry.is_dir():
            yield from _walk(entry)
        else:
            try:
                yield str(entry), entry.read_bytes()
            except Exception:  # noqa: BLE001 - unreadable entry; skip
                continue


def _programs() -> Iterator[tuple[str, bytes]]:
    """Yield (label, bytes) for every tokenised BASIC program in the corpus."""
    images = (
        sorted(_WORKSPACE_ROOT.glob("tests/**/*.ssd"))
        + sorted(_WORKSPACE_ROOT.glob("tests/**/*.dsd"))
        + sorted(_WORKSPACE_ROOT.glob("tests/**/*.adl"))
        + sorted(_WORKSPACE_ROOT.glob("tests/**/*.adf"))
    )
    for image in images:
        suffix = image.suffix.lower()
        try:
            if suffix in (".ssd", ".dsd"):
                from oaknut.dfs import DFS

                with DFS.from_file(image) as disc:
                    files = list(_walk(disc.root))
            else:
                from oaknut.adfs import ADFS

                with ADFS.from_file(image) as disc:
                    files = list(_walk(disc.root))
        except Exception:  # noqa: BLE001 - image that won't open; skip
            continue
        for name, data in files:
            if _looks_like_tokenised_basic(data):
                yield f"{image.name}:{name}", data


def test_real_programs_round_trip_byte_exactly():
    checked = 0
    regressions: list[str] = []
    fixed: list[str] = []
    for label, data in _programs():
        checked += 1
        try:
            round_trips = tokenise(detokenise(data)) == data
        except Exception:  # noqa: BLE001 - any codec failure counts as not round-tripping
            round_trips = False
        if round_trips and label in KNOWN_LIMITATIONS:
            fixed.append(label)
        elif not round_trips and label not in KNOWN_LIMITATIONS:
            regressions.append(label)

    assert checked >= _MIN_PROGRAMS_EXPECTED, (
        f"only {checked} programs found; expected >= {_MIN_PROGRAMS_EXPECTED} "
        f"(are the disc images present and opening?)"
    )
    assert not regressions, (
        "programs that used to round-trip now do not:\n  " + "\n  ".join(sorted(regressions))
    )
    # Not a failure, but flag known limitations that now pass so the list
    # can be trimmed (e.g. after a crunch fix lands).
    if fixed:
        print("\nKNOWN_LIMITATIONS entries that now round-trip (remove them):")
        for label in sorted(fixed):
            print(f"  {label}")
