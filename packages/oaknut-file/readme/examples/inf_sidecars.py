"""Formatting and parsing both INF dialects."""

from oaknut.file import (
    Access,
    format_pieb_inf_line,
    format_trad_inf_line,
    parse_inf_line,
)

# Traditional INF: filename load exec length [attr]
trad = format_trad_inf_line(
    filename="HELLO",
    load_address=0x1900,
    exec_address=0x8023,
    length=0x100,
    attr=int(Access.R | Access.W),
)
print(trad)

# PiEconetBridge INF: owner load exec perm, in PiEB's own perm layout
pieb = format_pieb_inf_line(
    load_address=0xFFFFDD00,
    exec_address=0xFFFFDD00,
    attr=int(Access.R | Access.W | Access.L | Access.PR),
)
print(pieb)

# Auto-detect the dialect on parse; access comes back as the Acorn byte
source, meta = parse_inf_line(trad)
print(source, hex(meta.load_address), hex(meta.exec_address), hex(meta.access))

source, meta = parse_inf_line(pieb)
print(source, hex(meta.load_address), hex(meta.access), hex(meta.infer_filetype()))
