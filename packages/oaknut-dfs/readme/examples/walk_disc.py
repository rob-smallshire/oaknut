"""Walking every directory of a DFS disc."""

from oaknut.dfs import DFS

with DFS.from_file("disc.ssd") as dfs:
    for dirpath, dirnames, filenames in dfs.root.walk():
        for name in filenames:
            print(dirpath / name)
