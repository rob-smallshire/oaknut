"""The image-decoder axis: non-sector images decoded on the way into a reader."""

from __future__ import annotations

import pytest
from oaknut.filesystem import (
    DecodedImage,
    ImageDecoder,
    ReadOnlyFilesystemError,
    reader_for,
)
from oaknut.filesystem.decoder import clear_decode_cache, decoder_for


class FakeDecoder(ImageDecoder):
    """Decodes FAKE images by dropping the magic."""

    extensions = frozenset({".fake"})

    def __init__(self, name: str = "fake"):
        super().__init__(name=name)
        self.calls = 0

    def recognises(self, prefix: bytes) -> bool:
        return prefix.startswith(b"FAKE")

    def decode(self, data: bytes) -> DecodedImage:
        self.calls += 1
        return DecodedImage(data[4:], suffix=".ssd", format_name="Fake v1", notes=("n",))


@pytest.fixture
def fake():
    clear_decode_cache()
    return FakeDecoder()


def test_recognised_bytes_are_decoded(fake):
    with reader_for(b"FAKEpayload", decoders={"fake": fake}) as reader:
        assert reader.read(0, 7) == b"payload"
        assert reader.suffix == ".ssd"
        assert reader.decoded.format_name == "Fake v1"
        assert reader.decoded.notes == ("n",)
        assert not reader.writable


def test_unrecognised_bytes_pass_through(fake):
    with reader_for(b"plain", decoders={"fake": fake}) as reader:
        assert reader.read(0, 5) == b"plain"
        assert reader.decoded is None


def test_recognised_file_is_decoded(fake, tmp_path):
    filepath = tmp_path / "disc.fake"
    filepath.write_bytes(b"FAKEcontent")
    with reader_for(filepath, decoders={"fake": fake}) as reader:
        assert reader.read(0, 7) == b"content"
        assert reader.suffix == ".ssd"


def test_a_decoded_file_cannot_be_opened_for_writing(fake, tmp_path):
    filepath = tmp_path / "disc.fake"
    filepath.write_bytes(b"FAKEcontent")
    with pytest.raises(ReadOnlyFilesystemError, match="Fake v1.*read-only"):
        reader_for(filepath, writable=True, decoders={"fake": fake})


def test_decoding_a_file_is_cached_until_it_changes(fake, tmp_path):
    filepath = tmp_path / "disc.fake"
    filepath.write_bytes(b"FAKEcontent")
    for _ in range(3):
        reader_for(filepath, decoders={"fake": fake}).close()
    assert fake.calls == 1
    filepath.write_bytes(b"FAKEchanged!")
    with reader_for(filepath, decoders={"fake": fake}) as reader:
        assert reader.read(0, 8) == b"changed!"
    assert fake.calls == 2


def test_decoder_for_matches_on_the_prefix(fake):
    assert decoder_for(b"FAKE...", {"fake": fake}) is fake
    assert decoder_for(b"nope", {"fake": fake}) is None
