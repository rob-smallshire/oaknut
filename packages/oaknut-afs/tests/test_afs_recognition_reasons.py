"""AFS says why it declines an image (#82)."""

from __future__ import annotations

from oaknut.filesystem import Rejection, create_filesystem, reader_for


def _reason(image: bytes) -> str:
    with reader_for(bytes(image)) as reader:
        verdict = create_filesystem("afs").probe(reader)
    assert isinstance(verdict, Rejection), verdict
    assert verdict.filesystem == "afs"
    return verdict.reason


def test_no_magic_names_what_was_found():
    assert _reason(b"\x00" * 204800) == (
        "no AFS0 info sector: sector 1 starts with 00 00 00 00, not 'AFS0'"
    )


def test_printable_bytes_are_shown_as_text():
    image = bytearray(204800)
    image[256:260] = b"Hugo"
    assert "starts with 'Hugo'" in _reason(image)


def test_a_malformed_info_sector_says_so():
    image = bytearray(204800)
    image[256:260] = b"AFS0"
    image[260:276] = b"\x01" * 16  # a disc name of control characters
    assert _reason(image).startswith("AFS0 info sector in sector 1 is malformed: ")
