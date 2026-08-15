# oaknut-extension

[![PyPI version](https://img.shields.io/pypi/v/oaknut-extension)](https://pypi.org/project/oaknut-extension/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-extension)](https://pypi.org/project/oaknut-extension/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-extension)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-extension/LICENSE)

The entry-point plug-in framework shared by every extensible *axis* of the
`oaknut` package family.

An **axis** is one extension point — a family of interchangeable plug-ins that
all answer the same question. The primary axis is *filesystems* (each plug-in
detects and operates on one disc format, in `oaknut-filesystem`);
`oaknut.command` (CLI subcommands contributed by filesystem packages) is
another.

Each axis declares a `kind` (a short identifier such as `"filesystem"`).
Concrete extensions for that axis subclass `Extension`, override `_kind()`,
and register themselves under the `oaknut.<kind>` entry-point namespace in
their package's `pyproject.toml`:

```toml
[project.entry-points."oaknut.filesystem"]
acorn-dfs = "oaknut.dfs.filesystem:AcornDFS"
```

Consumers discover and load them through `list_extensions()`,
`create_extension()`, and friends, which wrap [stevedore](https://docs.openstack.org/stevedore/).
Because discovery is by installed entry point, a plug-in shipped by any package
appears automatically — no central registry to edit.

This package is deliberately domain-agnostic: it knows nothing about discs,
files, or formats. It depends only on `oaknut-exception` (for the shared error
hierarchy) and `stevedore`.

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## Installation

```sh
uv add oaknut-extension    # or: pip install oaknut-extension
```

## License

MIT — see [LICENSE](LICENSE).
