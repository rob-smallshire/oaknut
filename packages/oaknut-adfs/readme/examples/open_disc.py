"""Opening an ADFS image and reading its root directory."""

from oaknut.adfs import ADFS

with ADFS.from_file("RISCOS.adf") as adfs:
    print(adfs.title)

    # Navigate with a pathlib-inspired API; "$" is the root.
    for entry in (adfs.root / "$").iterdir():
        s = entry.stat()
        print(f"{entry.name:12s} {s.length:7d}  load={s.load_address:08X}")

    data = (adfs.root / "$" / "ReadMe").read_bytes()
    print(len(data), "bytes")
