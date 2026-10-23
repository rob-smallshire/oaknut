"""Unshown context for the README's fragments: a blank double-sided image."""

from oaknut.discimage import DiscImage, UnifiedDisc, interleaved_double_sided_specs

buffer = memoryview(bytearray(2 * 80 * 10 * 256))
specs = interleaved_double_sided_specs(num_tracks=80, sectors_per_track=10)
