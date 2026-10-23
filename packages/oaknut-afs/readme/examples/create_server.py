"""Creating a Level 3 File Server disc with one user."""

from oaknut.afs import AFS, UserSpec

with AFS.create_file(
    "server.dat",
    capacity="10MB",
    disc_name="Server",
    users=[UserSpec(name="RJS", quota="2MB")],
) as afs:
    # Creating the RJS account also creates its home directory, $.RJS.
    (afs.root / "RJS" / "ReadMe").write_text("Welcome to the file server.\n")
