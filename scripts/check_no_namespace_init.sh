#!/usr/bin/env bash
# Fail if any package has accidentally shipped src/oaknut/__init__.py.
#
# Every package in this workspace contributes to a shared PEP 420
# implicit namespace package called `oaknut`. If any package ships an
# __init__.py at the namespace root (rather than at the sub-package
# root), it shadows the namespace and breaks every sibling package's
# imports at install time. The failure mode is hard to diagnose —
# `import oaknut.file` just raises ImportError with no hint as to why
# — so we guard against it on every commit and in CI.
#
# Valid:   packages/oaknut-file/src/oaknut/file/__init__.py
# Invalid: packages/oaknut-file/src/oaknut/__init__.py

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
offenders=$(find "$repo_root/packages" -maxdepth 4 -type f \
    -path '*/src/oaknut/__init__.py' 2>/dev/null || true)

if [[ -n "$offenders" ]]; then
    echo "ERROR: Found src/oaknut/__init__.py files inside packages." >&2
    echo "These shadow the PEP 420 namespace and must be removed:" >&2
    echo "$offenders" >&2
    echo >&2
    echo "Each package's own code lives at src/oaknut/<name>/__init__.py," >&2
    echo "never at the src/oaknut/ level. See docs/monorepo.md for context." >&2
    exit 1
fi

exit 0
