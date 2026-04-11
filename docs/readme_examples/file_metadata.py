"""RISC OS filetype detection from an Acorn load address.

Demonstrates ``oaknut.file.AcornMeta`` recognising a filetype-stamped
load address of the form ``0xFFF?????``, where the top 12 bits are
the RISC OS filetype sentinel and bits 8–19 hold the filetype itself.
"""

from oaknut.file import AcornMeta

# A RISC OS file with the ArtWorks filetype (0xD94) stamped into its
# load address. The bottom byte is the low half of the date word.
meta = AcornMeta(load_addr=0xFFFD9400, exec_addr=0xFFF12345)

print(f"load_addr:         0x{meta.load_addr:08X}")
print(f"filetype-stamped:  {meta.is_filetype_stamped}")
print(f"inferred filetype: 0x{meta.infer_filetype():03X}")
