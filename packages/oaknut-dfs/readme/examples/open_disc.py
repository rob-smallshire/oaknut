"""Opening a DFS image and reading its catalogue."""

from oaknut.dfs import DFS

with DFS.from_file("Zalaga.ssd") as dfs:
    print(dfs.title)

    # Navigate with a pathlib-inspired API.
    for entry in dfs.root / "$":
        s = entry.stat()
        print(f"{entry.name:10s}  {s.length:6d}  load={s.load_address:08X}")

    # Read file data.
    data = (dfs.root / "$" / "ZALAGA").read_bytes()
    print(len(data), "bytes")
