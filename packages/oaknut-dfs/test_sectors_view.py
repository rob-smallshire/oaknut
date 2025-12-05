#!/usr/bin/env python3
"""Quick test of SectorsView functionality."""

import sys
sys.path.insert(0, 'src')

from oaknut_dfs.sectors_view import SectorsView

# Test 1: Single sector
print("Test 1: Single sector")
buffer = bytearray(b"A" * 256)
view = SectorsView([memoryview(buffer)])
print(f"Length: {len(view)}")
print(f"First byte: {view[0]}")
print(f"Slice [0:5]: {view[0:5]}")
print("✓ Single sector read works\n")

# Test 2: Multiple sectors (contiguous)
print("Test 2: Multiple contiguous sectors")
buffer = bytearray(b"A" * 256 + b"B" * 256)
views = [memoryview(buffer)[0:256], memoryview(buffer)[256:512]]
sv = SectorsView(views)
print(f"Length: {len(sv)}")
print(f"Byte 0: {chr(sv[0])}")
print(f"Byte 256: {chr(sv[256])}")
print(f"Slice [250:262]: {sv[250:262]}")
print("✓ Multiple sector read works\n")

# Test 3: Write to single sector
print("Test 3: Write to single sector")
buffer = bytearray(b"A" * 256)
view = SectorsView([memoryview(buffer)])
view[0] = ord('X')
view[10:15] = b"HELLO"
print(f"Byte 0: {chr(buffer[0])}")
print(f"Bytes 10-15: {buffer[10:15]}")
assert buffer[0] == ord('X')
assert buffer[10:15] == b"HELLO"
print("✓ Single sector write works\n")

# Test 4: Write across multiple sectors
print("Test 4: Write across multiple sectors")
buffer = bytearray(b"A" * 512)
views = [memoryview(buffer)[0:256], memoryview(buffer)[256:512]]
sv = SectorsView(views)
sv[250:262] = b"HELLO_WORLD!"
print(f"Bytes 250-262 in buffer: {buffer[250:262]}")
assert buffer[250:262] == b"HELLO_WORLD!"
print("✓ Multi-sector write works\n")

# Test 5: tobytes()
print("Test 5: tobytes()")
buffer = bytearray(b"TEST" * 64)  # 256 bytes
view = SectorsView([memoryview(buffer)])
data = view.tobytes()
assert data == bytes(buffer)
print("✓ tobytes() works\n")

# Test 6: Empty sectors
print("Test 6: Empty sectors")
sv = SectorsView([])
assert len(sv) == 0
assert sv.tobytes() == b""
print("✓ Empty sectors work\n")

print("=" * 50)
print("All tests passed!")
