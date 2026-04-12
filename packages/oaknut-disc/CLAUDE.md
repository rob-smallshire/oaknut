# CLAUDE.md -- oaknut-disc

Unified CLI for Acorn DFS, ADFS, and AFS disc images. See
`docs/cli-design.md` for the authoritative design document covering
every subcommand, the filing-system prefix convention, argument
ordering, Acorn star-aliases, and error model.

Depends on all library packages: oaknut-file, oaknut-dfs, oaknut-adfs,
oaknut-afs. Uses Click for command parsing and Rich for formatted
output.

Key architectural piece: `cli_paths.py` handles the `afs:`/`adfs:`/`dfs:`
filing-system prefix that routes commands to the correct partition.
