"""Recognising a filetype-stamped load address."""

from oaknut.file import AcornMeta

meta = AcornMeta(load_address=0xFFFF0E10)
print(meta.is_filetype_stamped, hex(meta.infer_filetype()))
