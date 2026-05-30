"""Disc titles must be reported without on-disc padding.

DFS title fields are fixed-width and padded — conventionally with
spaces, but real-world images (and some writers) NUL-pad instead. The
padding is not part of the title, so reading it back must strip both.
"""

import pytest
from oaknut.dfs.dfs import DFS
from oaknut.dfs.formats import (
    ACORN_DFS_80T_SINGLE_SIDED,
    WATFORD_DFS_80T_SINGLE_SIDED,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_ZALAGA = REFERENCE_IMAGES_DIRPATH / "games" / "Disc003-Zalaga.ssd"

# Acorn DFS splits the 12-char title across sector 0 (bytes 0-7) and sector 1
# (bytes 0-3); Watford's 10-char title is sector 0 (bytes 0-7) + sector 1
# (bytes 0-1).
_ACORN_TITLE_SPANS = ((0, 0, 8), (256, 0, 4))
_WATFORD_TITLE_SPANS = ((0, 0, 8), (256, 0, 2))


def _image_with_nul_title(source_filepath, target_filepath, title: bytes, spans) -> None:
    """Write *target_filepath* as a copy of *source_filepath* whose raw title
    field holds *title*, NUL-padded.

    The poked bytes are written to a **fresh** path, never back over the
    source: ``DFS.create_file`` leaves the source memory-mapped until its
    handle is garbage-collected, and on Windows a mapped file cannot be
    truncated — which ``write_bytes`` does — so rewriting it raises
    ``OSError(EINVAL)`` there. Reading the source and writing a new file
    sidesteps that.
    """
    data = bytearray(source_filepath.read_bytes())
    cursor = 0
    for base, start, length in spans:
        chunk = title[cursor : cursor + length]
        data[base + start : base + start + length] = chunk.ljust(length, b"\x00")
        cursor += length
    target_filepath.write_bytes(bytes(data))


class TestDFSTitlePadding:
    @pytest.mark.parametrize(
        "disc_format,spans",
        [
            (ACORN_DFS_80T_SINGLE_SIDED, _ACORN_TITLE_SPANS),
            (WATFORD_DFS_80T_SINGLE_SIDED, _WATFORD_TITLE_SPANS),
        ],
        ids=["acorn", "watford"],
    )
    def test_nul_padding_stripped(self, disc_format, spans, tmp_path):
        created_filepath = tmp_path / "created.ssd"
        padded_filepath = tmp_path / "padded.ssd"
        with DFS.create_file(created_filepath, disc_format, title="HELLO"):
            pass
        # DFS create space-pads, so plant a NUL-padded title explicitly —
        # into a fresh file, not back over the still-mapped source.
        _image_with_nul_title(created_filepath, padded_filepath, b"GAME", spans)
        with DFS.from_file(padded_filepath, disc_format) as dfs:
            assert dfs.title == "GAME"

    @pytest.mark.parametrize(
        "disc_format",
        [ACORN_DFS_80T_SINGLE_SIDED, WATFORD_DFS_80T_SINGLE_SIDED],
        ids=["acorn", "watford"],
    )
    def test_space_padding_stripped(self, disc_format, tmp_path):
        image_filepath = tmp_path / "spaced.ssd"
        with DFS.create_file(image_filepath, disc_format, title="DEMO"):
            pass
        with DFS.from_file(image_filepath, disc_format) as dfs:
            assert dfs.title == "DEMO"

    def test_real_image_nul_padded_title(self):
        # Disc003-Zalaga.ssd carries the NUL-padded title "ZALAG-L".
        with DFS.from_file(_ZALAGA) as dfs:
            assert dfs.title == "ZALAG-L"
            assert "\x00" not in dfs.title
