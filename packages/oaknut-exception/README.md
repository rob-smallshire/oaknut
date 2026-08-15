# oaknut-exception

[![PyPI version](https://img.shields.io/pypi/v/oaknut-exception)](https://pypi.org/project/oaknut-exception/)
[![CI](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml/badge.svg)](https://github.com/rob-smallshire/oaknut/actions/workflows/ci.yml)
[![Python versions](https://img.shields.io/pypi/pyversions/oaknut-exception)](https://pypi.org/project/oaknut-exception/)
[![License: MIT](https://img.shields.io/pypi/l/oaknut-exception)](https://github.com/rob-smallshire/oaknut/blob/master/packages/oaknut-exception/LICENSE)

Categorised exceptions and a CLI error-reporting boundary for the
`oaknut-*` family of packages.

The package defines a small exception hierarchy that every other
`oaknut-*` package's domain errors slot into:

- `OaknutException` — root of the hierarchy. Carries an `exit_code`
  property derived from the BSD `sysexits.h` set (via the `exit-codes`
  package).
- `DataError` — the operation failed because of the *data* it was given
  (a user-supplied path, a corrupted on-disc structure, an unsupported
  filetype). No traceback at the CLI boundary.
- `ConfigurationError` — the operation failed because of a runtime
  environment / configuration issue. No traceback at the CLI boundary.
- `InternalError` — the operation failed because something went wrong
  inside the library. **Traceback retained** at the CLI boundary so
  the report-an-issue path is obvious.

Plus a single error-handling boundary helper:

- `handled_errors` — a context manager (also usable as a decorator)
  that catches `DataError` and `ConfigurationError`, prints them via a
  caller-supplied printer, and exits with the most appropriate
  `ExitCode`. `InternalError` and unexpected exceptions propagate so
  their tracebacks reach the user. `KeyboardInterrupt` exits with the
  conventional `128 + SIGINT` status.

This package is what every `oaknut-disc`-like CLI uses to map library
errors onto stable exit codes without dropping into try/except in every
command.

See the [oaknut documentation](https://rob-smallshire.github.io/oaknut/)
for the full API reference.

Part of the [oaknut](https://github.com/rob-smallshire/oaknut) monorepo.

## Installation

```sh
uv add oaknut-exception    # or: pip install oaknut-exception
```

## License

MIT — see [LICENSE](LICENSE).
