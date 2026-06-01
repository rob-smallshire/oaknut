#!/usr/bin/env bash
# Fail if any package has accidentally shipped an __init__.py at a
# namespace-package level.
#
# Every package in this workspace contributes to a shared PEP 420
# implicit namespace package called `oaknut`. `oaknut.econet` is itself
# a further namespace package, so that oaknut-econet-core, -aun, -piconet
# and -hat can each contribute sub-packages under it from separate
# distributions. If any package ships an __init__.py at either namespace
# level (rather than at a concrete sub-package root), it shadows the
# namespace and breaks every sibling package's imports at install time.
# The failure mode is hard to diagnose — `import oaknut.file` just raises
# ImportError with no hint as to why — so we guard against it on every
# commit and in CI.
#
# Valid:   packages/oaknut-file/src/oaknut/file/__init__.py
#          packages/oaknut-econet-aun/src/oaknut/econet/aun/__init__.py
# Invalid: packages/oaknut-file/src/oaknut/__init__.py
#          packages/oaknut-econet-aun/src/oaknut/econet/__init__.py

set -euo pipefail

repo_root="$(cd "$(dirname "$0")/.." && pwd)"
offenders=$(find "$repo_root/packages" -maxdepth 5 -type f \
    \( -path '*/src/oaknut/__init__.py' \
       -o -path '*/src/oaknut/econet/__init__.py' \) 2>/dev/null || true)

if [[ -n "$offenders" ]]; then
    echo "ERROR: Found __init__.py at a namespace-package level inside packages." >&2
    echo "These shadow a PEP 420 namespace and must be removed:" >&2
    echo "$offenders" >&2
    echo >&2
    echo "Concrete code lives one level deeper — at src/oaknut/<name>/__init__.py" >&2
    echo "or, under the econet namespace, src/oaknut/econet/<name>/__init__.py —" >&2
    echo "never at the src/oaknut/ or src/oaknut/econet/ level. See" >&2
    echo "docs/dev/monorepo.md and docs/dev/econet-design.md for context." >&2
    exit 1
fi

exit 0
