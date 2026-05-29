"""The AFS disc name must be reported without on-disc padding.

The 16-byte disc-name field is space-padded on disc; some images NUL-pad.
Neither is part of the name, while internal spaces are rejected at write
time, so a decoded name never carries padding.
"""

from oaknut.afs.info_sector import _DISC_NAME_LENGTH, _decode_disc_name


class TestAFSDiscNamePadding:
    def test_space_padding_stripped(self):
        raw = b"ARCHIVE".ljust(_DISC_NAME_LENGTH, b" ")
        assert _decode_disc_name(raw) == "ARCHIVE"

    def test_nul_padding_stripped(self):
        raw = b"ARCHIVE".ljust(_DISC_NAME_LENGTH, b"\x00")
        assert _decode_disc_name(raw) == "ARCHIVE"

    def test_mixed_trailing_padding_stripped(self):
        raw = b"FS".ljust(_DISC_NAME_LENGTH - 4, b" ") + b"\x00\x00\x00\x00"
        assert _decode_disc_name(raw) == "FS"

    def test_full_width_name_unpadded(self):
        raw = b"SIXTEENCHARNAME!"  # exactly 16 chars, no padding
        assert _decode_disc_name(raw) == "SIXTEENCHARNAME!"
