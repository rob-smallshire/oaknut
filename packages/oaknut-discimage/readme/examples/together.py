"""Writing through a surface into the backing buffer."""

from oaknut.discimage import DiscImage, single_sided_spec

buffer = memoryview(bytearray(b"\x00" * (80 * 10 * 256)))  # 80T × 10 sectors
image = DiscImage(buffer, [single_sided_spec(num_tracks=80, sectors_per_track=10)])

surface = image.surface(0)
sector0 = surface.sector_range(0, 1)
sector0[0:8] = b"MYDISC  "  # write the catalogue title into sector 0
assert bytes(buffer[0:8]) == b"MYDISC  "  # it landed in the backing buffer
