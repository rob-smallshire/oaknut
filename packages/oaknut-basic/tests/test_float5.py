"""Tests for the BBC BASIC 5-byte packed REAL codec.

The golden vectors come straight from the BBC BASIC II ROM constant pool
(see the floating-point analysis doc): the packed form is *exponent-first*,
``[exp, sign+sig_MSB, sig_2, sig_3, sig_LSB]`` — the same order the ROM
stores its constants in (e.g. ``e`` = ``82 2D F8 54 58``).
"""

from __future__ import annotations

import math

import pytest
from oaknut.basic.exceptions import Float5RangeError
from oaknut.basic.float5 import pack_float5, unpack_float5

# Packed (natural, exponent-first) bytes -> value. Drawn from the ROM.
ROM_CONSTANTS = [
    ("822df85458", 2.718281827867031),  # e        (&AAE4)
    ("81490fdaa2", math.pi / 2),  # pi/2     (&AA63)
    ("80317217f8", math.log(2)),  # ln 2     (&A86E)
    ("8100000000", 1.0),
    ("8200000000", 2.0),
    ("8000000000", 0.5),
    ("8180000000", -1.0),
    ("0000000000", 0.0),
]


class TestUnpack:
    @pytest.mark.parametrize(("packed_hex", "value"), ROM_CONSTANTS)
    def test_unpacks_rom_constants(self, packed_hex: str, value: float) -> None:
        assert unpack_float5(bytes.fromhex(packed_hex)) == pytest.approx(value, rel=0, abs=1e-9)

    def test_zero_exponent_is_zero(self) -> None:
        assert unpack_float5(b"\x00\xff\xff\xff\xff") == 0.0

    def test_rejects_wrong_length(self) -> None:
        with pytest.raises(ValueError):
            unpack_float5(b"\x81\x00\x00\x00")


class TestPack:
    @pytest.mark.parametrize(("packed_hex", "value"), ROM_CONSTANTS)
    def test_packs_to_rom_bytes(self, packed_hex: str, value: float) -> None:
        # e is a truncation in the ROM, so packing true e need not reproduce it;
        # every other vector is exact and must round-trip to the stored bytes.
        if packed_hex == "822df85458":
            pytest.skip("ROM e is a deliberate truncation; covered by round-trip test")
        assert pack_float5(value) == bytes.fromhex(packed_hex)

    def test_negative_zero_packs_as_zero(self) -> None:
        assert pack_float5(-0.0) == b"\x00\x00\x00\x00\x00"

    def test_significand_carry_renormalises(self) -> None:
        # A mantissa that rounds up to 1.0 must carry into the exponent
        # rather than overflow the 32-bit significand.
        assert pack_float5(1.0 - 2**-34) == bytes.fromhex("8100000000")

    def test_overflow_raises(self) -> None:
        with pytest.raises(Float5RangeError):
            pack_float5(1e40)

    def test_underflow_flushes_to_zero(self) -> None:
        # The BBC format has no denormals; tiny magnitudes underflow to zero.
        assert pack_float5(1e-40) == b"\x00\x00\x00\x00\x00"


class TestRoundTrip:
    @pytest.mark.parametrize(("packed_hex", "_value"), ROM_CONSTANTS)
    def test_bytes_round_trip_through_value(self, packed_hex: str, _value: float) -> None:
        packed = bytes.fromhex(packed_hex)
        assert pack_float5(unpack_float5(packed)) == packed

    @pytest.mark.parametrize(
        "value",
        [3.14159, -2.5, 100.0, -0.001, 1234.5678, 1e30, -1e-30, 42.0],
    )
    def test_value_round_trips_within_precision(self, value: float) -> None:
        recovered = unpack_float5(pack_float5(value))
        assert recovered == pytest.approx(value, rel=2**-31)
