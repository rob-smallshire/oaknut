# oaknut-cli

Shared CLI toolkit for the [oaknut](https://github.com/rob-smallshire/oaknut)
family. It sits *below* the filesystem packages so that both the `disc`
CLI (`oaknut-disc`) and a filesystem's own contributed commands can
depend on it without a dependency cycle.

It provides the **contributed-command axis** — discovery of Click
commands a filesystem package registers on the `oaknut.command`
entry-point namespace — and report-rendering helpers shared between the
generic `disc` commands and the contributed ones.

See `docs/dev/contributed-commands.md` for the design.
