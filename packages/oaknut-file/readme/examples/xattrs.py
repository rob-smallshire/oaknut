"""Writing and reading Acorn metadata as extended attributes."""

from pathlib import Path

from oaknut.file import read_acorn_xattrs, write_acorn_xattrs

Path("myfile.bin").write_bytes(b"data")

# Write to the user.acorn.* namespace
write_acorn_xattrs(
    "myfile.bin",
    load_address=0x1900,
    exec_address=0x8023,
    attr=0x03,
)

# Read back (falls through to user.econet_* if user.acorn.* is absent)
meta = read_acorn_xattrs("myfile.bin")
print(hex(meta.load_address), hex(meta.exec_address), hex(meta.access))
