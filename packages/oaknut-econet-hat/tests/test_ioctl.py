"""Hermetic check that the ioctl request numbers match the Linux encoding.

Getting these wrong is a silent hardware failure, so they are verified against
the values implied by PiEconetBridge's econet-gpio-consumer.h (magic 0xa9).
"""

import struct

from oaknut.econet.hat.gpio import (
    IOC_AUNMODE,
    IOC_READMODE,
    IOC_RESET,
    IOC_SET_STATIONS,
    IOC_TXERR,
)


def test_io_numbers_without_argument():
    assert IOC_RESET == 0xA900  # _IO(0xa9, 0)
    assert IOC_READMODE == 0xA909  # _IO(0xa9, 9)


def test_iow_and_ior_int_numbers():
    assert IOC_AUNMODE == 0x4004A906  # _IOW(0xa9, 6, int)
    assert IOC_TXERR == 0x8004A908  # _IOR(0xa9, 8, int)


def test_set_stations_number_uses_the_platform_pointer_size():
    pointer_size = struct.calcsize("P")
    assert IOC_SET_STATIONS == (1 << 30) | (pointer_size << 16) | (0xA9 << 8) | 5
