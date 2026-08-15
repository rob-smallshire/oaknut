# oaknut-codecs

[![PyPI version](https://img.shields.io/pypi/v/oaknut-codecs)](https://pypi.org/project/oaknut-codecs/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-codecs)](https://pypi.org/project/oaknut-codecs/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-codecs)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-codecs/LICENSE)

Text codecs for Acorn computer character sets, part of the
[oaknut](https://github.com/rob-smallshire/oaknut) family of packages for
working with Acorn computer filesystems, files, and formats.

This package provides a Python codec for the **Acorn/BBC Micro character
set** — a variant of ASCII in which `&60` is the pound sign `£` and `&7C`
is the broken bar `¦`. Importing the package registers the codec under
the name `"acorn"`, so it works with the standard `str.encode` /
`bytes.decode` machinery:

```python
import oaknut.codecs  # registers the "acorn" codec

"COST£100".encode("acorn")   # b'COST\x60100'
b"COST\x60100".decode("acorn")  # 'COST£100'
```

It is the dependency-free bottom layer of the workspace, alongside
`oaknut-exception`, so that language and file packages can share one
codec implementation without taking a dependency on each other.

## Installation

```sh
uv add oaknut-codecs
```

## License

MIT — see [LICENSE](LICENSE).
