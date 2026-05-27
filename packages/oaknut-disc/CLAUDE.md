# CLAUDE.md -- oaknut-disc

Unified CLI for Acorn DFS, ADFS, and AFS disc images. See
`docs/dev/cli-design.md` for the authoritative design document covering
every subcommand, the filing-system prefix convention, argument
ordering, Acorn star-aliases, and error model.

Depends on the `oaknut-cli` kit and the filesystem packages' `[cli]`
extras (`oaknut-dfs[cli]`, `oaknut-adfs[cli]`, `oaknut-afs[cli]`), which
contribute their commands through the `oaknut.command` entry-point axis.
The core library packages stay Click-free. Uses Click for command
parsing and asyoulikeit for formatted output.

`oaknut-disc` itself imports **no** filesystem package — content-first
identification and partition selection go through `oaknut.identify` plus
the filesystem extension manager in `mount.py`. `cli_paths.py` is now
only the fused `IMAGE_SPEC:PATH_SPEC` colon parser; the `afs:`/`adfs:`/
`dfs:` selector prefix it preserves is interpreted by `split_selector`
in `mount.py`.
