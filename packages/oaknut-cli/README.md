# oaknut-cli

[![PyPI version](https://img.shields.io/pypi/v/oaknut-cli)](https://pypi.org/project/oaknut-cli/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-cli)](https://pypi.org/project/oaknut-cli/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-cli)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-cli/LICENSE)

Shared CLI toolkit for the [oaknut](https://github.com/rob-smallshire/oaknut)
family. It sits *below* the filesystem packages so that both the `disc`
CLI (`oaknut-disc`) and a filesystem's own contributed commands can
depend on it without a dependency cycle.

It provides the **contributed-command axis** — discovery of Click
commands a filesystem package registers on the `oaknut.command`
entry-point namespace — and report-rendering helpers shared between the
generic `disc` commands and the contributed ones.

See `docs/dev/contributed-commands.md` for the design.

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## Installation

```sh
uv add oaknut-cli    # or: pip install oaknut-cli
```

## License

MIT — see [LICENSE](LICENSE).
