"""Create an in-memory DFS disc image, write a file, read it back.

Shows the oaknut.dfs public API for the most common task: open or
create a disc, work with files through a ``pathlib.Path``-like API,
and inspect catalogue metadata.
"""

from oaknut.dfs import DFS
from oaknut.dfs.formats import ACORN_DFS_40T_SINGLE_SIDED

# Create a blank 40-track single-sided DFS image in memory. The
# catalogue is initialised empty with the supplied title.
dfs = DFS.create(ACORN_DFS_40T_SINGLE_SIDED, title="WELCOME")

# Files live under the catalogue root. The "$" directory is the
# default if you write a bare filename.
(dfs.root / "HELLO").write_bytes(b'PRINT "Hello, World!"')

print(f"title:        {dfs.title!r}")
print(f"files:        {[str(f.path) for f in dfs.files]}")
print(f"free_sectors: {dfs.free_sectors}")
