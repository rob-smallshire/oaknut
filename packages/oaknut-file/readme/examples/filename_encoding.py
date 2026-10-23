"""Reading and writing filename metadata suffixes."""

from oaknut.file import AcornMeta, build_filename_suffix, parse_encoded_filename

# RISC OS filetype suffix (3 hex digits)
clean, meta = parse_encoded_filename("PROG,ffb")
print(clean, hex(meta.infer_filetype()))

# Load-exec suffix (variable-width hex), as HostFS and LanManFS write it
clean, meta = parse_encoded_filename("PROG,1900-801f")
print(clean, hex(meta.load_address), hex(meta.exec_address))

# Writing: ,xxx for a filetyped file, ,load-exec otherwise
print(build_filename_suffix(AcornMeta(load_address=0xFFFFFB00, exec_address=0)))
print(build_filename_suffix(AcornMeta(load_address=0x1900, exec_address=0x8023)))

# &FFFF1900 carries the filetype marker; say when the words are addresses
io_meta = AcornMeta(load_address=0xFFFF1900, exec_address=0xFFFF8023)
print(build_filename_suffix(io_meta))
print(build_filename_suffix(io_meta, typed_metadata=False))
