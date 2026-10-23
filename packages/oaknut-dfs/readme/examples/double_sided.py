"""Opening each side of a double-sided image."""

from oaknut.dfs import DFS

with DFS.from_file("game.dsd") as side0:
    print(side0.title)

with DFS.from_file("game.dsd", side=1) as side2:
    print(side2.title)
