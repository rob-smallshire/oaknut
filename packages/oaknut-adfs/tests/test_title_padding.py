"""ADFS directory titles must be reported without on-disc padding.

ADFS pads the 19-byte title field with CR (0x0D); foreign writers may
use NUL or trailing spaces. None of that padding is part of the title,
and internal spaces (a multi-word title) must survive.
"""

from helpers.adfs_image import make_adfs_s_image
from oaknut.adfs.adfs import ADFS


def _title_of(root_title: str) -> str:
    buf = make_adfs_s_image(root_title=root_title)
    adfs = ADFS.from_buffer(memoryview(bytearray(buf)))
    return adfs.root.title


class TestADFSTitlePadding:
    def test_cr_padding_stripped(self):
        # The helper pads the title field with CR — ADFS's own convention.
        assert _title_of("HELLO") == "HELLO"

    def test_trailing_spaces_stripped(self):
        assert _title_of("HELLO   ") == "HELLO"

    def test_internal_spaces_preserved(self):
        # Only trailing padding goes; a multi-word title is intact.
        assert _title_of("Game Collection") == "Game Collection"

    def test_empty_title(self):
        assert _title_of("") == ""
