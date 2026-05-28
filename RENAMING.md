# Ubiquitous-language path-vocabulary rename

Working file for the `refactor/ubiquitous-path-vocabulary` branch.
**This file is transient — deleted in the final commit of the
branch.** It holds the naming map, the stage checklist, and a
one-line status per stage so a session continuation can pick up
where the previous one left off without re-deriving context.

## Naming map

| Old | New |
|---|---|
| `image_spec` / `IMAGE_SPEC` | `outer_path` / `OUTER_PATH` |
| `path_spec` / `PATH_SPEC` | `inner_path` / `INNER_PATH` |
| `file_spec` / `FILE_SPEC` | `compound_path` / `COMPOUND_PATH` |
| `parse_file_spec()` | `parse_compound_path()` |
| `_split_at_image_colon()` | `_split_at_outer_colon()` |
| `in_image_path` (variable) | `inner_path` |
| `_FILE_SPEC_RE` (if present) | `_COMPOUND_PATH_RE` |
| Test class `TestParseImageArg` | `TestParseCompoundPath` |
| Test method `test_file_spec_required` | `test_compound_path_required` |

**Metavar in `--help`** (for every command that takes a compound
path): `OUTER:INNER`. The Click argument name itself is
`compound_path`; each `@click.argument` decorator sets
`metavar="OUTER:INNER"` explicitly so the user-visible form is
structural and uniform across all 21 commands.

## Out of scope (do NOT rename)

- **`_IMAGE_SPEC` dict** in `packages/oaknut-afs/scripts/build_library_images.py`
  — build-time mapping of library-image name to source dirs.
  Unrelated to CLI path vocabulary.
- **`split_selector(...)`** function name in `mount.py` — splits the
  partition `afs:`/`adfs:`/`acorn-dfs:` selector prefix off an inner
  path. The parameter renames (`in_image_path` → `inner_path`) but
  the function name stays — "selector" is the concept being split
  off, not "outer" or "inner".
- **Test class names already on the new vocabulary** in
  `test_cli_for_each.py`: `TestInnerPathMode` and
  `TestCompoundPathMode` — already correct from the for-each branch.

## Stage checklist

- [x] Stage 0 — Create this tracking file
- [x] Stage 1 — `cli_paths.py`: rename `parse_file_spec`,
  `_split_at_image_colon`, params, docstrings
- [ ] Stage 2 — `mount.py`: rename `resolve_mount` parameter,
  `in_image_path` variables, docstrings
- [ ] Stage 3 — `cli.py`: 21 `@click.argument` decorators, function
  parameters, bodies, docstrings; consolidate `in_image_path`/
  `in_image`/`in_path` → `inner_path`
- [ ] Stage 4 — Tests: 4 test files, ~30 occurrences
- [ ] Stage 5 — Documentation: 8 .rst files; rewrite `paths.rst` as
  canonical OUTER/INNER/COMPOUND
- [ ] Stage 6 — Final cleanup pass: grep, pytest, docs, pre-commit
- [ ] Stage 7 — Delete this tracking file

## Per-stage status

| Stage | Status | Commit | Notes |
|---|---|---|---|
| 0 | done | 0e0e088 | tracking file |
| 1 | done | (next) | cli_paths.py rewrite |
| 2 | pending | — | |
| 3 | pending | — | |
| 4 | pending | — | |
| 5 | pending | — | |
| 6 | pending | — | |
| 7 | pending | — | |

## Verification at end

1. `uv run pytest -q` → 2896+ passing (no test count regression)
2. `bash scripts/build_docs.sh` → html + coverage + doctest all clean
3. `pre-commit run --all-files` → clean
4. `grep -rIn "file_spec\|FILE_SPEC\|image_spec\|IMAGE_SPEC\|path_spec\|PATH_SPEC" packages docs scripts`
   returns ONLY the AFS `_IMAGE_SPEC` dict — anything else is a
   straggler.
5. `uv run disc ls --help` (and 2-3 other commands) show
   `OUTER:INNER` metavar.
