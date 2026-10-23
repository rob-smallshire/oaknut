"""Creating a new DFS disc and saving files to it."""

from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS

with DFS.create_file("demo.ssd", ACORN_DFS_80T_SINGLE_SIDED, title="DEMO") as dfs:
    (dfs.root / "$.HELLO").write_bytes(b"Hello, World!", load_address=0x1900)
    (dfs.root / "$.README").write_bytes(b"oaknut-dfs demo disc")

with DFS.from_file("demo.ssd") as dfs:
    print(dfs.title, [str(f.path) for f in dfs.files])
