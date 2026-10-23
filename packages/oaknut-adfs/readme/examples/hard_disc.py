"""Creating a New-map hard-disc image sized from a capacity."""

from oaknut.adfs import ADFS

# Size a New-map hard disc from a capacity; big_directories=True selects
# the Big directory (E+/F+) layout.
adfs = ADFS.create_new_map_hard_disc("40MB", title="IDEDisc", big_directories=True)
print(adfs.title, adfs.total_size, adfs.free_space)
