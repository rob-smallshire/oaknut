#!/usr/bin/env bash
# Build the oaknut documentation site — the single source of truth for
# the docs pipeline, used both locally and by CI
# (.github/workflows/{ci,release}.yml) so the two cannot drift.
#
# Each docs/<body>/ that contains a conf.py is an independent Sphinx
# project, built into _site/<body>/. The portal landing page
# (docs/portal/) sits at the site root. Output lands in the top-level,
# git-ignored _site/ directory.
#
# Usage:
#   scripts/build_docs.sh [html|coverage|doctest|all]
#
#   html      Build every body's HTML into _site/<body> (-W: warnings
#             are errors) and copy the portal landing page. Building the
#             disc manual also runs every scripts/cli-examples/*.py
#             recipe, so a broken or stale example fails the build.
#   coverage  Run scripts/check_doc_coverage.py: CLI command/example
#             coverage of the command reference, then each manual's
#             public-API __all__ coverage against its built objects.inv
#             (so the html phase must run first).
#   doctest   Execute every .. doctest:: block against the real library.
#   all       html, then coverage, then doctest (the default).
#
# Requires uv; Sphinx, the theme, and the coverage checker's deps come
# from the "docs" dependency group, pulled in on demand by
# `uv run --group docs`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

SITE_DIRPATH="_site"

# The packages each manual body documents, for the public-API coverage
# check. A body not listed here is still built and command-checked, but
# has no API-coverage gate.
api_packages_for_body() {
  case "$1" in
    disc) echo "oaknut.file oaknut.extension oaknut.discimage oaknut.filesystem oaknut.dfs oaknut.adfs oaknut.afs" ;;
    basic) echo "oaknut.basic" ;;
    zip) echo "oaknut.zip" ;;
    *) echo "" ;;
  esac
}

# Collapsible log groups under GitHub Actions; plain headers locally.
group_start() {
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then echo "::group::$1"; else echo "==> $1"; fi
}
group_end() {
  if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then echo "::endgroup::"; fi
}

doc_bodies() {
  for conf in docs/*/conf.py; do
    basename "$(dirname "$conf")"
  done
}

build_html() {
  for body in $(doc_bodies); do
    group_start "Building $body"
    # -E -a: always read every source afresh and write all output. Our
    # manuals embed live library output (the oaknut-command directive)
    # and freshly-executed cli-example transcripts, so Sphinx's
    # incremental model — which only rebuilds when an .rst source
    # changes — would silently leave docs stale after a code or
    # dependency change.
    uv run --group docs sphinx-build -E -a -b html "docs/$body" "$SITE_DIRPATH/$body" -W
    group_end
  done
  cp docs/portal/index.html "$SITE_DIRPATH/index.html"
  cp docs/portal/oaknut-logo.png "$SITE_DIRPATH/oaknut-logo.png"
}

check_coverage() {
  group_start "Coverage: CLI commands"
  uv run --group docs python scripts/check_doc_coverage.py commands
  group_end
  for body in $(doc_bodies); do
    packages="$(api_packages_for_body "$body")"
    [[ -z "$packages" ]] && continue
    group_start "Coverage: $body public API"
    # shellcheck disable=SC2086  # word-split $packages into separate args
    uv run --group docs python scripts/check_doc_coverage.py api \
      --inventory "$SITE_DIRPATH/$body/objects.inv" $packages
    group_end
  done
}

run_doctests() {
  for body in $(doc_bodies); do
    group_start "Doctest $body"
    # -E: fresh environment so doctests run against the current library.
    uv run --group docs sphinx-build -E -b doctest "docs/$body" "docs/$body/_build/doctest" -W
    group_end
  done
}

case "${1:-all}" in
  html) build_html ;;
  coverage) check_coverage ;;
  doctest) run_doctests ;;
  all)
    build_html
    check_coverage
    run_doctests
    ;;
  *)
    echo "usage: $0 [html|coverage|doctest|all]" >&2
    exit 2
    ;;
esac
