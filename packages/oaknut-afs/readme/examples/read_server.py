"""Reading the server disc back."""

from oaknut.afs import AFS

with AFS.from_file("server.dat") as afs:
    for entry in afs.root.iterdir():
        print(entry.name)
    text = (afs.root / "RJS" / "ReadMe").read_text()
    print(text, end="")
