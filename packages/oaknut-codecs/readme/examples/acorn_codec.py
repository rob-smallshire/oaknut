"""Encoding and decoding with the acorn codec."""

import oaknut.codecs  # registers the "acorn" codec

print("COST£100".encode("acorn"))
print(b"COST\x60100".decode("acorn"))
