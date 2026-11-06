"""HFE images through the oaknut.decoder axis: identify and mount as usual."""

from __future__ import annotations

import pytest
from oaknut.filesystem import ReadOnlyFilesystemError, identify, reader_for
from oaknut.filesystem.decoder import registered_decoders
from oaknut.hfe.container import write_hfe
from oaknut.hfe.decoder import HFEDecoder
from oaknut.hfe.exceptions import HFEError

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

HFE_DIRPATH = REFERENCE_IMAGES_DIRPATH / "hfe"
DUNJUNZ_S1_FILEPATH = HFE_DIRPATH / "Dunjunz_D1S1_40T_HG3_8518BF40_1.hfe"


def test_registered_on_the_decoder_axis():
    assert isinstance(registered_decoders()["hfe"], HFEDecoder)


def test_recognises_both_signatures():
    decoder = HFEDecoder(name="hfe")
    assert decoder.recognises(b"HXCPICFE" + bytes(504))
    assert decoder.recognises(b"HXCHFEV3" + bytes(504))
    assert not decoder.recognises(b"HXCHFEV2" + bytes(504))


def test_reader_reads_the_flattened_sectors():
    with reader_for(DUNJUNZ_S1_FILEPATH) as reader:
        assert reader.size == 102_400
        assert reader.suffix == ".ssd"
        assert reader.read(0, 8) == b"MASTER 1"
        assert reader.decoded.format_name == "HFE v3"
        assert reader.decoded.notes == ("FM, 40 tracks, 1 side(s), 10 x 256 bytes",)


def test_identified_as_acorn_dfs():
    best = identify(DUNJUNZ_S1_FILEPATH)[0]
    assert best.filesystem == "acorn-dfs"


def test_cannot_be_opened_for_writing():
    with pytest.raises(ReadOnlyFilesystemError, match="HFE v3"):
        reader_for(DUNJUNZ_S1_FILEPATH, writable=True)


def test_an_image_with_no_readable_sectors():
    with pytest.raises(HFEError, match="no readable sectors"):
        HFEDecoder(name="hfe").decode(write_hfe([["10" * 1000]]))
