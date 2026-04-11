# Acorn Character Encoding

This document describes the character encoding used by Acorn computers (BBC Micro, Acorn Electron) and how it's handled in the oaknut-dfs library.

## Background

The BBC Micro and Acorn Electron used a variant of ASCII with some UK-specific character substitutions. This was common among British computers of the 1980s, which adapted the 7-bit ASCII character set to include the pound sign (£) and other UK-specific characters.

## Character Set Differences

### BBC Micro (MODEs 0-6)

The BBC Micro made the following character substitutions:

| Decimal | Hex  | Standard ASCII | BBC Micro Display |
|---------|------|----------------|-------------------|
| 96      | 0x60 | `` ` `` (backtick) | `£` (pound sign) |
| 124     | 0x7C | `|` (vertical bar) | `¦` (broken bar) |

### MODE 7 (Teletext)

MODE 7 had additional character substitutions for Teletext compatibility, but these are not used in DFS disk images.

### Character Range

- **0-31:** Control characters (not translated)
- **32-95, 97-123, 125-255:** Standard ASCII (unchanged)
- **96 (0x60):** Pound sign (£)
- **124 (0x7C):** Broken bar (¦)

## Implementation

### Python Codec

The oaknut-dfs library implements Acorn encoding as a proper Python codec, registered under the name `'acorn'`. This allows standard Python encoding/decoding operations:

```python
# Encoding Unicode to Acorn bytes
text = "COST£100"
data = text.encode('acorn')  # b'COST\x60100'

# Decoding Acorn bytes to Unicode
data = b"PRICE:\x60500"
text = data.decode('acorn')  # "PRICE:£500"
```

### Codec Features

**Encoding:**
- Converts Unicode strings to Acorn byte representation
- Translates `£` → `0x60` and `¦` → `0x7C`
- All other characters below 256 pass through unchanged
- Characters above 255 raise `UnicodeEncodeError` (or are handled per error mode)

**Decoding:**
- Converts Acorn bytes to Unicode strings
- Translates `0x60` → `£` and `0x7C` → `¦`
- All other bytes pass through as their Unicode equivalents

**Error Handling:**
The codec supports standard Python error handling modes:
- `strict` (default): Raise `UnicodeEncodeError` on unencodable characters
- `ignore`: Skip unencodable characters
- `replace`: Replace unencodable characters with `?`

```python
# Strict mode (raises exception)
try:
    "TEST™".encode('acorn')
except UnicodeEncodeError:
    print("Cannot encode trademark symbol")

# Ignore mode (skips invalid characters)
result = "TEST™OK".encode('acorn', errors='ignore')  # b'TESTOK'

# Replace mode (uses ? for invalid characters)
result = "TEST™".encode('acorn', errors='replace')  # b'TEST?'
```

### Stream Support

The codec works with Python's text I/O wrapper for file operations:

```python
import io

# Write using Acorn encoding
buffer = io.BytesIO()
writer = io.TextIOWrapper(buffer, encoding='acorn')
writer.write("£100")
writer.flush()

# Read using Acorn encoding
buffer.seek(0)
reader = io.TextIOWrapper(buffer, encoding='acorn')
text = reader.read()  # "£100"
```

## Usage in oaknut-dfs

### Internal Use Only

The Acorn encoding is used **internally** within the catalog layer (Layer 3) when reading and writing:
- Disk titles (12 characters)
- Filenames (7 characters)
- Directory names (1 character)

**Users never need to know about the encoding.** The public API (Layers 3 and 4) uses standard Python Unicode strings.

### Example: Catalog Layer

```python
# Internal implementation (catalog.py)
def read_disk_info(self):
    sector0 = self._sector_image.read_sector(0)
    sector1 = self._sector_image.read_sector(1)

    # Decode using Acorn encoding
    title_part1 = sector0[0:8].decode("acorn")
    title_part2 = sector1[0:4].decode("acorn")
    title = (title_part1 + title_part2).rstrip()

    return DiskInfo(title=title, ...)

def write_disk_info(self, info):
    # Encode using Acorn encoding
    title = info.title[:12].ljust(12)
    sector0[0:8] = title[0:8].encode("acorn")
    sector1[0:4] = title[8:12].encode("acorn")
    ...
```

### User-Facing API

Users work with normal Python strings containing Unicode characters:

```python
from oaknut_dfs import DFSImage

# Create disk with pound sign in title
disk = DFSImage.create("game.ssd", title="COST: £50")

# Save file with pound sign in name
disk.save("£MONEY", data, load_addr=0x1900, exec_addr=0x1900)

# List files - returns Unicode strings
for file in disk.cat():
    print(file.full_name)  # Might print "$.£MONEY"
```

The encoding/decoding happens transparently behind the scenes.

## Filename Constraints

### Valid Characters

Acorn DFS filenames typically contain:
- **Uppercase letters:** A-Z
- **Digits:** 0-9
- **Punctuation:** `!#$%&()+-.@^_`
- **UK characters:** `£`

### Invalid Characters

- Lowercase letters (should be converted to uppercase)
- Spaces
- Special characters: `*/?\\:<>`
- Characters outside the 0-255 range

### Sanitization

The `sanitize_for_acorn()` helper function cleans strings for use as filenames:

```python
from oaknut_dfs.acorn_encoding import sanitize_for_acorn

# Converts to uppercase and removes invalid characters
clean = sanitize_for_acorn("test*file.bin")  # "TESTFILE.BIN"
clean = sanitize_for_acorn("my file")        # "MYFILE"
clean = sanitize_for_acorn("COST£100")       # "COST£100"
```

## Historical Context

### Why Different Encodings?

In the early 1980s, computers were limited to 7-bit or 8-bit character sets. The full ASCII standard (128 characters, 0-127) didn't include currency symbols, so different manufacturers chose different substitutions:

- **BBC Micro:** `0x60` (backtick) → `£`
- **Commodore 64:** `0x5C` (backslash) → `£`
- **Oric:** `0x5F` (underscore) → `£`
- **Acorn Archimedes:** `0xA3` → `£` (ISO Latin-1 standard position)

The BBC Micro's choice of `0x60` was pragmatic - the backtick character was rarely used in British computing, making it a sensible character to replace.

### International Standards

The UK national variant of ISO 646 (standardized in 1985) took a different approach:
- `0x23` encoded `£` instead of `#`
- `0x7E` encoded overline instead of `~`

However, the BBC Micro's character set predates this standard and uses different positions.

## Technical Details

### Codec Registration

The codec is automatically registered when the `oaknut_dfs.acorn_encoding` module is imported:

```python
import oaknut_dfs.acorn_encoding  # Registers 'acorn' codec

# Now available system-wide
text.encode('acorn')
bytes.decode('acorn')
```

### Implementation

The codec is implemented using Python's standard `codecs` module:

- `AcornCodec`: Main codec class with `encode()` and `decode()` methods
- `AcornIncrementalEncoder/Decoder`: Support for incremental encoding/decoding
- `AcornStreamWriter/Reader`: Support for text I/O streams
- Registration via `codecs.register(search_function)`

### Source Code

The implementation can be found in:
- `src/oaknut_dfs/acorn_encoding.py` - Codec implementation
- `tests/test_acorn_encoding.py` - Comprehensive test suite

## References

- [BeebWiki: ASCII](https://beebwiki.mdfs.net/ASCII) - BBC Micro character set documentation
- [Acorn Electron User Guide: Appendix F](https://www.acornelectron.co.uk/ugs/electron/acorn_computers/ug-english/appendix_f_eng.html) - Character set tables
- [MOS: Chapter 4](https://tobylobster.github.io/mos/mos/S-s4.html) - Character definitions and VDU tables
- [Wikipedia: Pound sign](https://en.wikipedia.org/wiki/Pound_sign) - Historical context on currency symbol encoding

## Summary

The Acorn character encoding is a simple variant of ASCII with two character substitutions for UK-specific symbols. In oaknut-dfs:

1. **Implementation:** Proper Python codec registered as `'acorn'`
2. **Usage:** Internal only - used by catalog layer when reading/writing disk sectors
3. **Public API:** Users work with Unicode strings, encoding is transparent
4. **Compatibility:** 1-to-1 mapping ensures perfect round-trip fidelity

This design keeps the implementation historically accurate while providing a modern, Pythonic interface to users.
