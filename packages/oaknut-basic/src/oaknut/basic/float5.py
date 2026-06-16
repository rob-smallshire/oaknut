"""The BBC BASIC 5-byte packed floating-point (REAL) format.

A packed BBC REAL is five bytes, *exponent first* — the order the
language ROM stores its constant pool in:

======  ============================================================
offset  byte
======  ============================================================
+0      exponent (excess-128 bias; ``0`` means the whole value is zero)
+1      sign (bit 7) and significand MSB (bits 6-0), implied leading 1 dropped
+2      significand byte 2
+3      significand byte 3
+4      significand byte 4 (LSB)
======  ============================================================

The significand is a normalised 32-bit fraction in ``[0.5, 1)``, so its
top bit is always 1; the format reuses that bit for the sign and treats
the leading 1 as implied. Decoding restores it::

    value = (-1)**sign * significand * 2**(exponent - 160)

The ``-160`` folds together the ``-128`` exponent bias and the ``2**-32``
that turns the 32-bit integer significand back into a fraction.

These functions work in the *natural* exponent-first order. BBC data
files (``PRINT#``) write the five bytes **reversed** on the wire; that
reversal belongs to the record codec, not here.
"""

from __future__ import annotations

import math

from oaknut.basic.exceptions import Float5RangeError

# Bias folding -128 (excess-128 exponent) and -32 (32-bit significand -> fraction).
_EXPONENT_FOLD = 160
_FLOAT5_LENGTH = 5


def unpack_float5(packed: bytes) -> float:
    """Decode five exponent-first packed bytes into a Python float.

    Args:
        packed: Exactly five bytes in natural (exponent-first) order.

    Returns:
        The decoded value. A zero exponent decodes to ``0.0`` regardless
        of the remaining bytes.

    Raises:
        ValueError: If *packed* is not exactly five bytes long.
    """
    if len(packed) != _FLOAT5_LENGTH:
        raise ValueError(f"a packed BBC REAL is {_FLOAT5_LENGTH} bytes, got {len(packed)}")
    exponent = packed[0]
    if exponent == 0:
        return 0.0
    sign_and_msb = packed[1]
    negative = bool(sign_and_msb & 0x80)
    significand = (
        ((sign_and_msb | 0x80) << 24) | (packed[2] << 16) | (packed[3] << 8) | packed[4]
    )
    value = math.ldexp(significand, exponent - _EXPONENT_FOLD)
    return -value if negative else value


def pack_float5(value: float) -> bytes:
    """Encode a Python float into five exponent-first packed bytes.

    The 32-bit significand is rounded to nearest, ties to even. A tie
    that rounds the significand up to ``1.0`` carries into the exponent
    rather than overflowing. Magnitudes below the smallest normal
    underflow to zero (the format has no denormals).

    Args:
        value: A finite Python float.

    Returns:
        Five bytes in natural (exponent-first) order. ``0.0`` (and
        ``-0.0``) encode to five zero bytes.

    Raises:
        Float5RangeError: If *value* is non-finite or its magnitude is
            too large for the excess-128 exponent.
    """
    if value == 0.0:
        return b"\x00\x00\x00\x00\x00"
    if not math.isfinite(value):
        raise Float5RangeError(value)

    negative = math.copysign(1.0, value) < 0
    fraction, exponent = math.frexp(abs(value))  # 0.5 <= fraction < 1
    significand = round(math.ldexp(fraction, 32))  # round(fraction * 2**32), ties to even
    if significand == (1 << 32):  # rounded up to 1.0: carry into the exponent
        significand = 1 << 31
        exponent += 1

    biased_exponent = exponent + 128
    if biased_exponent > 0xFF:
        raise Float5RangeError(value)
    if biased_exponent < 1:  # underflow: no denormals
        return b"\x00\x00\x00\x00\x00"

    sign_and_msb = (significand >> 24) & 0x7F  # drop the implied leading 1
    if negative:
        sign_and_msb |= 0x80
    return bytes(
        (
            biased_exponent,
            sign_and_msb,
            (significand >> 16) & 0xFF,
            (significand >> 8) & 0xFF,
            significand & 0xFF,
        )
    )
