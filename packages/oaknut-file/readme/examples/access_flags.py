"""Composing Acorn access flags."""

from oaknut.file import Access

# Compose flags with bitwise OR
flags = Access.R | Access.W | Access.L
print(repr(flags))
print(hex(flags))
