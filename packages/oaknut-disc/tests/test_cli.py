"""Tests for the disc CLI commands.

Uses Click's CliRunner to drive each subcommand against in-memory
disc images created by the library fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli

# ---------------------------------------------------------------------------
# Version and help
# ---------------------------------------------------------------------------


class TestCLIBasics:
    def test_version(self, runner: CliRunner) -> None:
        from oaknut.disc import __version__

        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "ls" in result.output
        assert "cat" in result.output
        assert "create" in result.output

    def test_star_alias_cat_lowercase(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["*cat", str(dfs_image_filepath)])
        assert result.exit_code == 0

    def test_star_alias_cat_uppercase(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["*CAT", str(dfs_image_filepath)])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Inspection: ls
# ---------------------------------------------------------------------------


class TestLs:
    def test_ls_dfs_root(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        # --as display pins the Rich renderer so the format-label in the
        # table title ("DFS") is part of the output.  Default piped
        # output is TSV, which omits titles.
        result = runner.invoke(
            cli, ["ls", "--as", "display", str(dfs_image_filepath)]
        )
        assert result.exit_code == 0
        # Root shows the $ directory, not the files directly.
        assert "$" in result.output
        assert "DFS" in result.output

    def test_ls_dfs_dollar(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(dfs_image_filepath), "$"])
        assert result.exit_code == 0
        assert "HELLO" in result.output
        assert "DATA" in result.output

    def test_ls_adfs_root(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["ls", "--as", "display", str(adfs_image_filepath)]
        )
        assert result.exit_code == 0
        assert "Hello" in result.output
        assert "Games" in result.output
        assert "ADFS" in result.output

    def test_ls_adfs_subdirectory(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(adfs_image_filepath), "$.Games"])
        assert result.exit_code == 0
        assert "Elite" in result.output

    def test_ls_afs_prefix(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["ls", "--as", "display", str(afs_image_filepath), "afs:"]
        )
        assert result.exit_code == 0
        assert "AFS" in result.output

    def test_ls_nonexistent_path(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(dfs_image_filepath), "$.NOPE"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_ls_prefix_mismatch(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(dfs_image_filepath), "adfs:$"])
        assert result.exit_code != 0
        assert "cannot access as ADFS" in result.output


# ---------------------------------------------------------------------------
# Issue #12 — disc ls and disc stat must format AFS access bytes using the
# on-disc AFS bit layout, not the wire-form Acorn byte layout.
# ---------------------------------------------------------------------------


class TestAccessBytesFormattedCorrectlyOnAFS:
    @pytest.mark.parametrize(
        "filename, expected_attr",
        [
            ("alpha", "WR/R"),
            ("bravo", "LWR/R"),
            ("charlie", "WR/WR"),
            ("delta", "/"),
        ],
    )
    def test_ls_afs_attributes_match_written_access(
        self,
        runner: CliRunner,
        afs_image_with_access_bytes: Path,
        filename: str,
        expected_attr: str,
    ) -> None:
        result = runner.invoke(
            cli, ["ls", str(afs_image_with_access_bytes), "afs:$"]
        )
        assert result.exit_code == 0, result.output
        # Find the row for this file and check the Attr column matches
        # the AFS-form string the file was written with.
        row = next(
            (line for line in result.output.splitlines() if filename in line),
            None,
        )
        assert row is not None, f"no row for {filename!r} in:\n{result.output}"
        assert expected_attr in row, (
            f"expected {expected_attr!r} in row for {filename!r}, "
            f"got: {row!r}"
        )

    @pytest.mark.parametrize(
        "filename, expected_attr",
        [
            ("alpha", "WR/R"),
            ("bravo", "LWR/R"),
            ("charlie", "WR/WR"),
        ],
    )
    def test_stat_afs_attributes_match_written_access(
        self,
        runner: CliRunner,
        afs_image_with_access_bytes: Path,
        filename: str,
        expected_attr: str,
    ) -> None:
        result = runner.invoke(
            cli,
            ["stat", str(afs_image_with_access_bytes), f"afs:$.{filename}"],
        )
        assert result.exit_code == 0, result.output
        # Default piped output is TSV ("Attr\tWR/R"); display mode uses
        # a bordered table.  Match either by looking for Attr on a line
        # followed by the expected symbolic string.
        attr_line = next(
            ln for ln in result.output.splitlines() if "Attr" in ln
        )
        assert expected_attr in attr_line, attr_line

    def test_ls_afs_directory_shows_D_form(
        self,
        runner: CliRunner,
        afs_image_with_access_bytes: Path,
    ) -> None:
        """A directory must render with the ``D/`` form, not be
        misinterpreted as a file.
        """
        result = runner.invoke(
            cli, ["ls", str(afs_image_with_access_bytes), "afs:$"]
        )
        assert result.exit_code == 0, result.output
        # The ls code path renders directories as a separate row
        # without an Attr column — just verify the directory name
        # appears with the trailing slash convention and the row
        # doesn't leak a misformatted file-style attr for it.
        assert "Folder/" in result.output

    def test_ls_adfs_unchanged(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        """Regression: ADFS ls must still produce its wire-form
        Access rendering — the fix must not affect non-AFS paths.
        """
        result = runner.invoke(cli, ["ls", str(adfs_image_filepath)])
        assert result.exit_code == 0, result.output
        # ADFS files written without explicit access get default
        # owner R+W; rendered as "WR/" by format_access_text.
        assert "WR/" in result.output


# ---------------------------------------------------------------------------
# Issue #10 — disc ls --access-byte / -H shows the raw access byte as two
# hex digits alongside the symbolic column.
# ---------------------------------------------------------------------------


class TestLsAccessByteFlag:
    @pytest.mark.parametrize("flag", ["--access-byte", "-H"])
    def test_afs_access_byte_flag_shows_hex(
        self,
        runner: CliRunner,
        afs_image_with_access_bytes: Path,
        flag: str,
    ) -> None:
        """``--access-byte`` / ``-H`` adds a hex column for AFS files."""
        result = runner.invoke(
            cli, ["ls", flag, str(afs_image_with_access_bytes), "afs:$"]
        )
        assert result.exit_code == 0, result.output
        # WR/R on AFS = PR (0x01) + OR (0x04) + OW (0x08) = 0x0D.
        # The "0x" prefix makes it unambiguously hex and directly
        # copy-pasteable into ``disc chmod``.
        row = next(
            line for line in result.output.splitlines() if "alpha" in line
        )
        assert "0x0D" in row, f"expected 0x0D in row, got: {row!r}"
        assert "WR/R" in row, f"symbolic form must remain, got: {row!r}"

    def test_afs_access_byte_distinct_per_file(
        self,
        runner: CliRunner,
        afs_image_with_access_bytes: Path,
    ) -> None:
        result = runner.invoke(
            cli, ["ls", "-H", str(afs_image_with_access_bytes), "afs:$"]
        )
        assert result.exit_code == 0, result.output
        # Each file's hex byte appears on its own row, "0x"-prefixed.
        expected = {
            "alpha": "0x0D",    # WR/R
            "bravo": "0x1D",    # LWR/R
            "charlie": "0x0F",  # WR/WR
            "delta": "0x00",    # /
        }
        for name, hex_byte in expected.items():
            row = next(
                (line for line in result.output.splitlines() if name in line),
                None,
            )
            assert row is not None, f"no row for {name!r}"
            assert hex_byte in row, (
                f"expected {hex_byte!r} in row for {name!r}, got: {row!r}"
            )

    def test_adfs_access_byte_flag(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        """Flag also works on ADFS files."""
        result = runner.invoke(
            cli, ["ls", "-H", str(adfs_image_filepath)]
        )
        assert result.exit_code == 0, result.output
        # ADFS default write_bytes access is WR/R = owner R+W + public R
        # = wire byte R(0x01) | W(0x02) | PR(0x10) = 0x13.
        row = next(
            line for line in result.output.splitlines() if "Hello" in line
        )
        assert "0x13" in row, f"expected 0x13 in row, got: {row!r}"
        assert "WR/" in row

    def test_dfs_access_byte_flag(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        """DFS files: unlocked (0x00) and locked (0x08) render."""
        result = runner.invoke(cli, ["ls", "-H", str(dfs_image_filepath), "$"])
        assert result.exit_code == 0, result.output
        # Neither test file is locked — both should show 0x00.
        assert "0x00" in result.output

    def test_access_byte_round_trips_to_chmod(
        self,
        runner: CliRunner,
        afs_image_with_access_bytes: Path,
    ) -> None:
        """The displayed hex string feeds straight back into chmod.

        Guards against accidentally dropping the ``0x`` prefix (which
        ``parse_access`` would still accept for most values but at a
        round trip through the letter-disambiguation branch, e.g.
        ``"WR"`` would be symbolic not hex).
        """
        from oaknut.file import parse_access

        # Parse "0x0D" the way disc chmod parses its argument.
        # If the ls output format ever changed to a bare "0D", this
        # would still work — but "WR" (also two valid hex digits)
        # wouldn't, so insist on the explicit prefix.
        result = runner.invoke(
            cli, ["ls", "-H", str(afs_image_with_access_bytes), "afs:$"]
        )
        assert result.exit_code == 0, result.output
        row = next(line for line in result.output.splitlines() if "alpha" in line)
        # The row has cells separated by tabs in the default TSV
        # output (CliRunner has no TTY).  Either tab or Rich-border
        # splits pick out the 0x-prefixed cell.
        separators = "\t│"
        import re as _re

        tokens = [t for t in _re.split(f"[{separators}]", row) if "0x" in t]
        assert tokens, f"no 0x-prefixed token in row: {row!r}"
        hex_token = tokens[-1].strip()
        assert hex_token.startswith("0x")
        # Round-trip: parse_access must accept the ls output unchanged.
        assert int(parse_access(hex_token)) == 0x0D

    def test_default_ls_has_no_hex_column(
        self, runner: CliRunner, afs_image_with_access_bytes: Path
    ) -> None:
        """Without the flag the hex column is not added — a
        regression guard so the default ls output stays compact.
        """
        result = runner.invoke(
            cli, ["ls", str(afs_image_with_access_bytes), "afs:$"]
        )
        assert result.exit_code == 0, result.output
        # 0x-prefixed bytes must not leak into the default ls output.
        assert "0x0D" not in result.output
        assert "WR/R" in result.output


# ---------------------------------------------------------------------------
# Inspection: tree
# ---------------------------------------------------------------------------


class TestTree:
    def test_tree_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["tree", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "HELLO" in result.output

    def test_tree_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["tree", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "Games" in result.output
        assert "Elite" in result.output

    def test_tree_json_preserves_hierarchy(
        self, runner: CliRunner, adfs_image_tree: Path
    ) -> None:
        """--as json emits a nested document mirroring the tree."""
        import json as _json

        result = runner.invoke(
            cli, ["tree", "--as", "json", str(adfs_image_tree)]
        )
        assert result.exit_code == 0, result.output
        doc = _json.loads(result.output)
        payload = next(iter(doc["reports"].values()))
        roots = payload["roots"]
        assert len(roots) == 1
        names = _collect_names(roots[0])
        # The tree fixture has $ -> Root1, $ -> Dir -> Inside, $ -> Dir -> Sub -> Deep.
        assert "Root1" in names
        assert "Dir" in names
        assert "Sub" in names
        assert "Deep" in names

    def test_tree_multi_partition_json(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        import json as _json

        result = runner.invoke(
            cli,
            ["tree", "--as", "json", str(partitioned_image_with_files)],
        )
        assert result.exit_code == 0, result.output
        doc = _json.loads(result.output)
        payload = next(iter(doc["reports"].values()))
        # One root (the image filename) with ADFS and AFS labelled
        # partitions beneath it.
        assert len(payload["roots"]) == 1
        image_root = payload["roots"][0]
        partition_labels = [c["values"]["name"] for c in image_root["children"]]
        assert "ADFS" in partition_labels
        assert "AFS" in partition_labels


def _collect_names(node: dict) -> list[str]:
    """Flatten a tree-JSON node to a list of every descendant's name."""
    out = [node["values"]["name"]]
    for child in node.get("children", []):
        out.extend(_collect_names(child))
    return out


# ---------------------------------------------------------------------------
# Issue #14 — disc find must reach the AFS partition and emit full paths.
# ---------------------------------------------------------------------------


class TestFind:
    def test_find_dfs_bare_paths(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        """Single-partition DFS image: output stays unprefixed for
        backward compatibility.
        """
        result = runner.invoke(cli, ["find", str(dfs_image_filepath), "*"])
        assert result.exit_code == 0, result.output
        assert "$.HELLO" in result.output
        assert "$.DATA" in result.output
        assert "afs:" not in result.output
        assert "adfs:" not in result.output
        assert "dfs:" not in result.output

    def test_find_adfs_only_bare_paths(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        """Single-partition ADFS image: output stays unprefixed."""
        result = runner.invoke(cli, ["find", str(adfs_image_filepath), "*"])
        assert result.exit_code == 0, result.output
        assert "$.Hello" in result.output
        assert "afs:" not in result.output
        assert "adfs:" not in result.output

    def test_find_afs_prefix_returns_afs_paths(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        """Explicit ``afs:`` prefix scopes find to the AFS partition
        and returns full paths (currently a regression — AFS paths
        fall back to leaf names only because AFSPath has no ``.path``
        attribute).
        """
        result = runner.invoke(
            cli, ["find", str(partitioned_image_with_files), "afs:*"]
        )
        assert result.exit_code == 0, result.output
        assert "afs:$.afsA" in result.output
        assert "afs:$.GAMES.Elite" in result.output
        assert "afs:$.GAMES.Exile" in result.output
        # ADFS partition files must not leak into an afs-scoped search.
        assert "adfsA" not in result.output

    def test_find_adfs_prefix_returns_adfs_paths(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            ["find", str(partitioned_image_with_files), "adfs:*"],
        )
        assert result.exit_code == 0, result.output
        assert "adfs:$.adfsA" in result.output
        assert "adfs:$.adfsB" in result.output
        assert "afs:" not in result.output

    def test_find_multi_partition_no_prefix_enumerates_both(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        """With no prefix on a multi-partition image, find enumerates
        every partition and labels each result with its partition.
        """
        result = runner.invoke(
            cli, ["find", str(partitioned_image_with_files), "*"]
        )
        assert result.exit_code == 0, result.output
        assert "adfs:$.adfsA" in result.output
        assert "adfs:$.adfsB" in result.output
        assert "afs:$.afsA" in result.output
        assert "afs:$.GAMES.Elite" in result.output

    def test_find_afs_nested_pattern(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        """Nested pattern like ``afs:$.GAMES.*`` must match files
        under ``$.GAMES``.
        """
        result = runner.invoke(
            cli,
            [
                "find",
                str(partitioned_image_with_files),
                "afs:$.GAMES.*",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "afs:$.GAMES.Elite" in result.output
        assert "afs:$.GAMES.Exile" in result.output
        # afsA at AFS root must not match $.GAMES.*.
        assert "afsA" not in result.output

    def test_find_output_is_round_trippable(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        """Each line of find output should feed straight back into
        another command that understands the prefix syntax — the
        whole point of emitting prefixed paths on partitioned images.
        """
        result = runner.invoke(
            cli, ["find", str(partitioned_image_with_files), "afs:*"]
        )
        assert result.exit_code == 0, result.output
        # Skip header and comment lines; pick the first data line that
        # starts with the partition prefix.
        line = next(
            ln for ln in result.output.splitlines()
            if ln.startswith("afs:$.GAMES.Elite")
        )
        cat = runner.invoke(
            cli, ["cat", str(partitioned_image_with_files), line.strip()]
        )
        assert cat.exit_code == 0, cat.output
        assert b"e" in cat.output_bytes


# ---------------------------------------------------------------------------
# Issue #8 — --as display|tsv|json via asyoulikeit.
# ---------------------------------------------------------------------------


class TestFindAsFormats:
    """disc find emits a TableContent; --as selects the renderer."""

    def test_find_tsv_header_and_rows(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["find", "--as", "tsv", str(dfs_image_filepath), "*"]
        )
        assert result.exit_code == 0, result.output
        lines = [ln for ln in result.output.splitlines() if ln]
        # TSV header is prefixed with "# " per asyoulikeit convention.
        assert lines[0].startswith("#"), f"header row missing: {lines[0]!r}"
        data_rows = [ln for ln in lines if not ln.startswith("#")]
        assert "$.HELLO" in data_rows
        assert "$.DATA" in data_rows

    def test_find_json_parses(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        import json as _json

        result = runner.invoke(
            cli, ["find", "--as", "json", str(dfs_image_filepath), "*"]
        )
        assert result.exit_code == 0, result.output
        doc = _json.loads(result.output)
        # asyoulikeit JSON top level: {"reports": {name: {..., rows: [...]}}}
        assert "reports" in doc
        report_name, payload = next(iter(doc["reports"].items()))
        paths = [row["path"] for row in payload["rows"]]
        assert "$.HELLO" in paths
        assert "$.DATA" in paths

    def test_find_display_is_rich_table(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        """display mode produces a bordered Rich table."""
        result = runner.invoke(
            cli, ["find", "--as", "display", str(dfs_image_filepath), "*"]
        )
        assert result.exit_code == 0, result.output
        # Rich tables draw box-drawing chars.  Any presence of "│" or "┃"
        # confirms the display renderer ran.
        assert any(ch in result.output for ch in ("│", "┃"))
        assert "$.HELLO" in result.output

    def test_find_multi_partition_tsv_prefix(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ) -> None:
        """TSV rows carry the partition prefix on a multi-partition
        image so they round-trip into other commands unchanged.
        """
        result = runner.invoke(
            cli,
            [
                "find",
                "--as",
                "tsv",
                str(partitioned_image_with_files),
                "*",
            ],
        )
        assert result.exit_code == 0, result.output
        data = [
            ln for ln in result.output.splitlines()
            if ln and not ln.startswith("#")
        ]
        assert "adfs:$.adfsA" in data
        assert "afs:$.GAMES.Elite" in data


# ---------------------------------------------------------------------------
# Inspection: stat
# ---------------------------------------------------------------------------


class TestStat:
    def test_stat_disc_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["stat", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "TestDFS" in result.output
        assert "DFS" in result.output

    def test_stat_disc_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["stat", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "TestADFS" in result.output
        assert "ADFS" in result.output

    def test_stat_disc_afs(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["stat", str(afs_image_filepath), "afs:"])
        assert result.exit_code == 0
        assert "TestAFS" in result.output

    def test_stat_file(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["stat", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        assert "Hello" in result.output
        assert "00001900" in result.output
        assert "00008023" in result.output

    def test_stat_nonexistent(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["stat", str(dfs_image_filepath), "$.NOPE"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Issue #7 — disc stat must show a disc-level summary followed by one block
# per filing-system partition, with self-consistent byte/sector figures.
# ---------------------------------------------------------------------------


def _extract_sizes(output: str) -> list[tuple[int, int]]:
    """Return every ``X bytes (Y sectors)``-shaped pair from ``output``."""
    import re

    pairs = []
    pattern = re.compile(r"([\d,]+)\s*bytes\s*\((\d+)\s*sectors?\)")
    for match in pattern.finditer(output):
        bytes_value = int(match.group(1).replace(",", ""))
        sector_value = int(match.group(2))
        pairs.append((bytes_value, sector_value))
    return pairs


def _extract_size_lines(output: str) -> list[tuple[int, int]]:
    """Every ``Size X bytes (Y sectors)``-shaped line in order.

    Tolerant of both the old ``Size:  ...`` display form and the new
    ``Size\\t...`` TSV form that asyoulikeit emits.  Excludes ``Free``
    lines so callers can count by block (``disc + N partitions``)
    rather than by raw byte/sector pair.
    """
    import re

    pairs = []
    pattern = re.compile(
        r"^\s*Size\b[:\t\s]+([\d,]+)\s*bytes\s*\((\d+)\s*sectors?\)",
        re.MULTILINE,
    )
    for match in pattern.finditer(output):
        bytes_value = int(match.group(1).replace(",", ""))
        sector_value = int(match.group(2))
        pairs.append((bytes_value, sector_value))
    return pairs


class TestStatPartitionStructure:
    """Disc-level summary plus one block per partition."""

    def test_dfs_disc_and_single_partition(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        # Display mode pins the human-readable layout so the section
        # titles (Disc, Partition 1: DFS) appear as literal text.  TSV
        # omits titles by design.
        result = runner.invoke(
            cli, ["stat", "--as", "display", str(dfs_image_filepath)]
        )
        assert result.exit_code == 0, result.output
        assert "Disc" in result.output
        assert "Partition 1: DFS" in result.output
        # Title / boot option live under the partition now, not the disc.
        assert "TestDFS" in result.output
        # Byte/sector pairs must be self-consistent (issue #7 regression).
        for bytes_value, sector_value in _extract_sizes(result.output):
            assert bytes_value == sector_value * 256, (
                f"{bytes_value} bytes != {sector_value}*256"
            )

    def test_adfs_floppy_disc_and_single_partition(
        self, runner: CliRunner, adfs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["stat", "--as", "display", str(adfs_image_filepath)]
        )
        assert result.exit_code == 0, result.output
        assert "Disc" in result.output
        assert "Partition 1: ADFS" in result.output
        assert "TestADFS" in result.output
        # One partition — its size must equal the disc size.
        for bytes_value, sector_value in _extract_sizes(result.output):
            assert bytes_value == sector_value * 256

    def test_adfs_hard_no_afs_single_partition(
        self, runner: CliRunner, adfs_hard_no_afs_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["stat", "--as", "display", str(adfs_hard_no_afs_filepath)]
        )
        assert result.exit_code == 0, result.output
        assert "Partition 1: ADFS" in result.output
        # Without AFS there is no Partition 2.
        assert "Partition 2" not in result.output
        for bytes_value, sector_value in _extract_sizes(result.output):
            assert bytes_value == sector_value * 256

    def test_adfs_hard_with_afs_two_partitions(
        self, runner: CliRunner, adfs_hard_with_afs_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli,
            ["stat", "--as", "display", str(adfs_hard_with_afs_filepath)],
        )
        assert result.exit_code == 0, result.output
        assert "Partition 1: ADFS" in result.output
        assert "Partition 2: AFS" in result.output
        # Disc-level geometry is a 296-cylinder SCSI hard disc.
        assert "296 cylinders" in result.output
        assert "Split" in result.output       # ADFS title
        assert "TwinFS" in result.output      # AFS disc name
        # Every byte/sector pair must be self-consistent — this is the
        # specific regression the reporter asked to guard (issue #7).
        pairs = _extract_sizes(result.output)
        assert pairs, f"no byte/sector pairs found in:\n{result.output}"
        for bytes_value, sector_value in pairs:
            assert bytes_value == sector_value * 256, (
                f"{bytes_value} bytes != {sector_value}*256 in:\n{result.output}"
            )

    def test_adfs_hard_with_afs_partitions_sum_to_disc(
        self, runner: CliRunner, adfs_hard_with_afs_filepath: Path
    ) -> None:
        """ADFS partition sectors + AFS partition sectors must equal
        the disc sector count.  Detects the original symptom — a
        partition size that bears no relation to the physical disc.
        """
        result = runner.invoke(cli, ["stat", str(adfs_hard_with_afs_filepath)])
        assert result.exit_code == 0, result.output
        size_lines = _extract_size_lines(result.output)
        # One Size line per block: disc, then each partition.
        assert len(size_lines) == 3, (
            f"expected 3 Size lines (disc + 2 partitions), "
            f"got {size_lines!r}"
        )
        disc_sectors = size_lines[0][1]
        partition_sectors = size_lines[1][1] + size_lines[2][1]
        assert partition_sectors == disc_sectors, (
            f"partitions sum to {partition_sectors} sectors but "
            f"disc is {disc_sectors} sectors"
        )

    def test_adfs_hard_with_afs_omits_user_list(
        self, runner: CliRunner, adfs_hard_with_afs_filepath: Path
    ) -> None:
        """The disc summary is a whole-disc overview; an AFS user
        list belongs in ``disc afs-users``, not here.
        """
        result = runner.invoke(cli, ["stat", str(adfs_hard_with_afs_filepath)])
        assert result.exit_code == 0, result.output
        assert "holmes" not in result.output
        assert "Welcome" not in result.output

    def test_afs_prefix_stays_afs_scoped(
        self, runner: CliRunner, adfs_hard_with_afs_filepath: Path
    ) -> None:
        """``disc stat image.dat afs:`` scopes to the AFS partition —
        the ``afs:`` prefix explicitly asks for the AFS view, so the
        disc-level + multi-partition layout does not apply.
        """
        result = runner.invoke(
            cli, ["stat", str(adfs_hard_with_afs_filepath), "afs:"]
        )
        assert result.exit_code == 0, result.output
        # AFS-scoped view: disc name and AFS-specific fields, no
        # Partition N headings.
        assert "TwinFS" in result.output
        assert "Partition 1" not in result.output
        assert "Partition 2" not in result.output


# ---------------------------------------------------------------------------
# Inspection: cat
# ---------------------------------------------------------------------------


class TestCat:
    def test_cat_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        assert b"Hello world" in result.output_bytes

    def test_cat_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["cat", str(adfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        assert b"Hello ADFS" in result.output_bytes

    def test_cat_afs(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["cat", str(afs_image_filepath), "afs:$.Greeting"])
        assert result.exit_code == 0
        assert b"Hello AFS" in result.output_bytes

    def test_cat_directory_errors(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["cat", str(adfs_image_filepath), "$.Games"])
        assert result.exit_code != 0
        assert "directory" in result.output

    def test_cat_nonexistent(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.NOPE"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_type_alias(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["*type", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        assert b"Hello world" in result.output_bytes


# ---------------------------------------------------------------------------
# Inspection: validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_validate_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["validate", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "OK" in result.output


# ---------------------------------------------------------------------------
# File I/O: get
# ---------------------------------------------------------------------------


class TestGet:
    def test_get_to_file(self, runner: CliRunner, dfs_image_filepath: Path, tmp_path: Path) -> None:
        out = tmp_path / "hello.bin"
        result = runner.invoke(
            cli,
            [
                "get",
                str(dfs_image_filepath),
                "$.Hello",
                str(out),
            ],
        )
        assert result.exit_code == 0
        assert out.read_bytes() == b"Hello world"

    def test_get_to_stdout(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli,
            [
                "get",
                str(dfs_image_filepath),
                "$.Hello",
                "-",
            ],
        )
        assert result.exit_code == 0
        assert b"Hello world" in result.output_bytes


# ---------------------------------------------------------------------------
# File I/O: put
# ---------------------------------------------------------------------------


class TestPut:
    def test_put_dfs(self, runner: CliRunner, dfs_image_filepath: Path, tmp_path: Path) -> None:
        src = tmp_path / "payload.bin"
        src.write_bytes(b"new file data")
        result = runner.invoke(
            cli,
            [
                "put",
                str(dfs_image_filepath),
                "$.NewFile",
                str(src),
            ],
        )
        assert result.exit_code == 0

        # Verify the file was written.
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.NewFile"])
        assert result.exit_code == 0
        assert b"new file data" in result.output_bytes

    def test_put_adfs(self, runner: CliRunner, adfs_image_filepath: Path, tmp_path: Path) -> None:
        src = tmp_path / "payload.bin"
        src.write_bytes(b"adfs payload")
        result = runner.invoke(
            cli,
            [
                "put",
                str(adfs_image_filepath),
                "$.NewFile",
                str(src),
            ],
        )
        assert result.exit_code == 0

        result = runner.invoke(cli, ["cat", str(adfs_image_filepath), "$.NewFile"])
        assert result.exit_code == 0
        assert b"adfs payload" in result.output_bytes


# ---------------------------------------------------------------------------
# Modification: title, opt
# ---------------------------------------------------------------------------


class TestTitle:
    def test_read_title_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["title", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "TestDFS" in result.output

    def test_set_title_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["title", str(dfs_image_filepath), "NewTitle"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["title", str(dfs_image_filepath)])
        assert "NewTitle" in result.output

    def test_read_title_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["title", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "TestADFS" in result.output


class TestOpt:
    def test_read_opt_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "OFF" in result.output

    def test_set_opt_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath), "3"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath)])
        assert "EXEC" in result.output

    def test_set_opt_by_name_lowercase(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath), "run"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath)])
        assert "RUN" in result.output

    def test_set_opt_by_name_uppercase(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath), "LOAD"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath)])
        assert "LOAD" in result.output

    def test_set_opt_by_name_mixed_case(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath), "Exec"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath)])
        assert "EXEC" in result.output

    def test_set_opt_invalid_integer(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath), "5"])
        assert result.exit_code != 0

    def test_set_opt_invalid_name(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["opt", str(dfs_image_filepath), "banana"])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Modification: rm, lock, unlock
# ---------------------------------------------------------------------------


class TestRm:
    def test_rm_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["rm", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code != 0

    def test_rm_nonexistent_no_force(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["rm", str(dfs_image_filepath), "$.NOPE"])
        assert result.exit_code != 0

    def test_rm_nonexistent_force(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["rm", "-f", str(dfs_image_filepath), "$.NOPE"])
        assert result.exit_code == 0

    def test_rm_dry_run(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["rm", "--dry-run", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        assert "would remove" in result.output
        # File should still exist.
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0


class TestLockUnlock:
    def test_lock_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["lock", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0

    def test_unlock_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        # Lock then unlock.
        runner.invoke(cli, ["lock", str(dfs_image_filepath), "$.Hello"])
        result = runner.invoke(cli, ["unlock", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Modification: mv, cp
# ---------------------------------------------------------------------------


class TestMv:
    def test_mv_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli,
            [
                "mv",
                str(dfs_image_filepath),
                "$.Hello",
                "$.Greet",
            ],
        )
        assert result.exit_code == 0
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.Greet"])
        assert result.exit_code == 0
        assert b"Hello world" in result.output_bytes


class TestCp:
    def test_cp_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                str(dfs_image_filepath),
                "$.Hello",
                "$.Copy",
            ],
        )
        assert result.exit_code == 0
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.Copy"])
        assert result.exit_code == 0
        assert b"Hello world" in result.output_bytes
        # Original should still exist.
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0

    def test_cp_dfs_to_adfs(
        self, runner: CliRunner, dfs_image_filepath: Path, adfs_image_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_filepath}:$.HELLO",
                f"{adfs_image_filepath}:$.FromDFS",
            ],
        )
        assert result.exit_code == 0
        # Verify it arrived in the ADFS image.
        result = runner.invoke(cli, ["cat", str(adfs_image_filepath), "$.FromDFS"])
        assert result.exit_code == 0
        assert b"Hello world" in result.output_bytes

    def test_cp_adfs_to_dfs(
        self, runner: CliRunner, dfs_image_filepath: Path, adfs_image_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_filepath}:$.Hello",
                f"{dfs_image_filepath}:$.FrmADF",
            ],
        )
        assert result.exit_code == 0
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.FrmADF"])
        assert result.exit_code == 0
        assert b"Hello ADFS" in result.output_bytes

    def test_cp_cross_preserves_load_exec(
        self, runner: CliRunner, dfs_image_filepath: Path, adfs_image_filepath: Path,
    ) -> None:
        runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_filepath}:$.HELLO",
                f"{adfs_image_filepath}:$.Copied",
            ],
        )
        result = runner.invoke(
            cli, ["stat", str(adfs_image_filepath), "$.Copied"]
        )
        assert result.exit_code == 0
        assert "00001900" in result.output  # load address preserved
        assert "00008023" in result.output  # exec address preserved


# ---------------------------------------------------------------------------
# Issue #6 — disc cp globbing and recursive copy.
# ---------------------------------------------------------------------------


class TestCpGlob:
    """Source paths may carry Acorn wildcards (``*``, ``#``) that
    expand to zero or more leaves under a literal parent directory.
    When expanded, the destination must denote a directory.
    """

    def test_glob_star_within_dfs(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:$.*",
                f"{dfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        for name in ("Hello", "Help", "Data"):
            listed = runner.invoke(cli, ["ls", str(dfs_empty_filepath), "$"])
            assert name.upper() in listed.output, (
                f"{name} missing from destination:\n{listed.output}"
            )

    def test_glob_prefix_match_only(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        """``He*`` matches Hello and Help but not Data."""
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:$.He*",
                f"{dfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        listed = runner.invoke(cli, ["ls", str(dfs_empty_filepath), "$"])
        assert "HELLO" in listed.output
        assert "HELP" in listed.output
        assert "DATA" not in listed.output

    def test_glob_hash_single_char(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        """Acorn ``#`` wildcard matches exactly one character."""
        # "Hel#" should match Help but not Hello.
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:$.Hel#",
                f"{dfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        listed = runner.invoke(cli, ["ls", str(dfs_empty_filepath), "$"])
        assert "HELP" in listed.output
        assert "HELLO" not in listed.output

    def test_glob_no_matches_errors(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:$.Xyz*",
                f"{dfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code != 0
        assert "no match" in result.output.lower() or "match" in result.output.lower()

    def test_glob_dst_must_be_directory(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        """When the glob expands to multiple files, the destination
        cannot be a single leaf path.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:$.*",
                f"{dfs_empty_filepath}:$.Single",
            ],
        )
        assert result.exit_code != 0
        assert "directory" in result.output.lower()

    def test_glob_dfs_to_adfs(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """Glob crosses filing systems — DFS ``G.*`` lands under an
        ADFS subdirectory.
        """
        # Precreate destination directory.
        runner.invoke(cli, ["mkdir", str(adfs_empty_filepath), "$.GBucket"])
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:G.*",
                f"{adfs_empty_filepath}:$.GBucket/",
            ],
        )
        assert result.exit_code == 0, result.output
        listed = runner.invoke(cli, ["ls", str(adfs_empty_filepath), "$.GBucket"])
        assert "FOO" in listed.output
        assert "BAR" in listed.output

    def test_glob_preserves_load_exec(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """Per-file load/exec addresses must survive glob copy."""
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{dfs_image_many_files}:$.Hello",
                f"{adfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        stat = runner.invoke(cli, ["stat", str(adfs_empty_filepath), "$.Hello"])
        assert "00001900" in stat.output  # load address


class TestCpRecursive:
    """``-r`` / ``--recursive`` copies a source directory and its
    contents, creating intermediate destination directories as
    needed.
    """

    def test_recursive_copies_tree(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_image_tree}:$.Dir",
                f"{adfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        # Dir/Inside and Dir/Sub/Deep arrive under $.Dir on the dst.
        cat_inside = runner.invoke(
            cli, ["cat", str(adfs_empty_filepath), "$.Dir.Inside"]
        )
        assert cat_inside.exit_code == 0, cat_inside.output
        assert b"inside-data" in cat_inside.output_bytes
        cat_deep = runner.invoke(
            cli, ["cat", str(adfs_empty_filepath), "$.Dir.Sub.Deep"]
        )
        assert cat_deep.exit_code == 0, cat_deep.output
        assert b"deep-data" in cat_deep.output_bytes

    def test_recursive_rejects_directory_without_flag(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """A plain cp on a directory source must error and point at
        the ``-r`` flag.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_tree}:$.Dir",
                f"{adfs_empty_filepath}:$.DirCopy",
            ],
        )
        assert result.exit_code != 0
        assert "-r" in result.output or "recursive" in result.output.lower()

    def test_recursive_on_file_still_works(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """``-r`` on a file source is a no-op — it still copies the
        single file.  Matches Unix ``cp -r`` tolerance.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_image_tree}:$.Root1",
                f"{adfs_empty_filepath}:$.Solo",
            ],
        )
        assert result.exit_code == 0, result.output
        cat = runner.invoke(cli, ["cat", str(adfs_empty_filepath), "$.Solo"])
        assert b"root1-data" in cat.output_bytes

    def test_recursive_creates_intermediate_dirs(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """Recursive copy into a destination parent that doesn't
        exist yet creates it on the way.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_image_tree}:$.Dir",
                f"{adfs_empty_filepath}:$.New.Nested/",
            ],
        )
        assert result.exit_code == 0, result.output
        cat = runner.invoke(
            cli,
            ["cat", str(adfs_empty_filepath), "$.New.Nested.Dir.Sub.Deep"],
        )
        assert cat.exit_code == 0, cat.output
        assert b"deep-data" in cat.output_bytes

    def test_recursive_adfs_to_afs(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        adfs_hard_with_afs_filepath: Path,
    ) -> None:
        """Recursive copy across filing systems."""
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_image_tree}:$.Dir",
                f"{adfs_hard_with_afs_filepath}:afs:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        cat = runner.invoke(
            cli,
            ["cat", str(adfs_hard_with_afs_filepath), "afs:$.Dir.Sub.Deep"],
        )
        assert cat.exit_code == 0, cat.output
        assert b"deep-data" in cat.output_bytes

    def test_recursive_into_dfs_rejects_deeply_nested(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        """An ADFS tree that can't be flattened to DFS's one-level
        directory model must error rather than truncate.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_image_tree}:$.Dir",
                f"{dfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code != 0
        assert "dfs" in result.output.lower() or "flat" in result.output.lower() \
            or "nest" in result.output.lower()


class TestCpGlobRecursiveCombined:
    """Glob and ``-r`` compose — glob picks sources at the top level,
    each matched directory is recursed into.
    """

    def test_glob_with_recursive(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        runner.invoke(cli, ["mkdir", str(adfs_empty_filepath), "$.Archive"])
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_image_tree}:$.*",
                f"{adfs_empty_filepath}:$.Archive/",
            ],
        )
        assert result.exit_code == 0, result.output
        # File at top level.
        cat_root = runner.invoke(
            cli, ["cat", str(adfs_empty_filepath), "$.Archive.Root1"]
        )
        assert cat_root.exit_code == 0
        assert b"root1-data" in cat_root.output_bytes
        # Directory recursed.
        cat_deep = runner.invoke(
            cli,
            ["cat", str(adfs_empty_filepath), "$.Archive.Dir.Sub.Deep"],
        )
        assert cat_deep.exit_code == 0
        assert b"deep-data" in cat_deep.output_bytes


class TestCpDfsAdfsMapping:
    """Path mapping between DFS's flat-with-letter-prefix model and
    ADFS's hierarchical tree.

    Rule: ``D.F`` ↔ ``$.D.F``, with ``$.F`` ↔ ``$.F``.  Copying
    between filing systems applies the mapping so round-trips are
    lossless (see Rob's note on issue #6).
    """

    def test_dfs_dollar_is_transparent_into_adfs(
        self,
        runner: CliRunner,
        dfs_multi_dir_filepath: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """Files under DFS ``$`` land directly under ADFS ``$`` —
        there must be no spurious ``$`` subdirectory.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{dfs_multi_dir_filepath}:$",
                f"{adfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        listed = runner.invoke(cli, ["ls", str(adfs_empty_filepath), "$"])
        assert "HELLO" in listed.output
        assert "DATA" in listed.output
        # No "$" subdirectory spawned.
        assert "$/" not in listed.output

    def test_dfs_letter_dir_becomes_adfs_subdir(
        self,
        runner: CliRunner,
        dfs_multi_dir_filepath: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """Copying DFS ``A`` into ADFS creates an ``A`` subdirectory."""
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{dfs_multi_dir_filepath}:A",
                f"{adfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        listed = runner.invoke(
            cli, ["ls", str(adfs_empty_filepath), "$.A"]
        )
        assert "GAME" in listed.output

    def test_dfs_whole_image_to_adfs(
        self,
        runner: CliRunner,
        dfs_multi_dir_filepath: Path,
        adfs_empty_filepath: Path,
    ) -> None:
        """Recursive copy of the DFS virtual root: ``$`` children go
        to ADFS root, other letter directories become subdirectories.
        """
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{dfs_multi_dir_filepath}:",
                f"{adfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        # $.HELLO, $.DATA at root; A/GAME, G/FOO, G/BAR in subdirs.
        for bare in ("$.HELLO", "$.DATA", "$.A.GAME", "$.G.FOO", "$.G.BAR"):
            stat = runner.invoke(cli, ["stat", str(adfs_empty_filepath), bare])
            assert stat.exit_code == 0, (
                f"{bare} missing on destination: {stat.output!r}"
            )

    def test_adfs_one_level_tree_flattens_to_dfs(
        self,
        runner: CliRunner,
        dfs_multi_dir_filepath: Path,
        adfs_empty_filepath: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        """After going DFS → ADFS, coming back: ADFS root files go
        to DFS ``$``; ADFS single-char subdirs become DFS letter
        directories.
        """
        # Round-trip stage 1: DFS → ADFS.
        assert runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{dfs_multi_dir_filepath}:",
                f"{adfs_empty_filepath}:$/",
            ],
        ).exit_code == 0

        # Round-trip stage 2: ADFS → DFS.
        result = runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_empty_filepath}:$",
                f"{dfs_empty_filepath}:$/",
            ],
        )
        assert result.exit_code == 0, result.output
        for bare in ("$.HELLO", "$.DATA", "A.GAME", "G.FOO", "G.BAR"):
            stat = runner.invoke(cli, ["stat", str(dfs_empty_filepath), bare])
            assert stat.exit_code == 0, (
                f"{bare} missing on DFS destination: {stat.output!r}"
            )

    def test_full_roundtrip_preserves_bytes_and_metadata(
        self,
        runner: CliRunner,
        dfs_multi_dir_filepath: Path,
        adfs_empty_filepath: Path,
        dfs_empty_filepath: Path,
    ) -> None:
        """End-to-end DFS → ADFS → DFS round-trip.  Every source
        file must reappear with identical bytes, load address, exec
        address, and locked bit.
        """
        from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS

        # Snapshot the source.
        src_files: dict[str, dict] = {}
        with DFS.from_file(dfs_multi_dir_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            for entry in dfs.files:
                p = dfs.path(entry.path)
                st = p.stat()
                src_files[entry.path] = {
                    "bytes": p.read_bytes(),
                    "load": st.load_address,
                    "exec": st.exec_address,
                    "locked": st.locked,
                }

        # Round-trip.
        assert runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{dfs_multi_dir_filepath}:",
                f"{adfs_empty_filepath}:$/",
            ],
        ).exit_code == 0, "DFS→ADFS leg failed"
        assert runner.invoke(
            cli,
            [
                "cp",
                "-r",
                f"{adfs_empty_filepath}:$",
                f"{dfs_empty_filepath}:$/",
            ],
        ).exit_code == 0, "ADFS→DFS leg failed"

        # Compare.
        with DFS.from_file(dfs_empty_filepath, ACORN_DFS_80T_SINGLE_SIDED) as dfs:
            dst_files = {entry.path for entry in dfs.files}
            assert dst_files == set(src_files), (
                f"file set differs: {dst_files} vs {set(src_files)}"
            )
            for path_str, expected in src_files.items():
                p = dfs.path(path_str)
                st = p.stat()
                assert p.read_bytes() == expected["bytes"], path_str
                assert st.load_address == expected["load"], (
                    f"{path_str}: load {st.load_address:#x} vs "
                    f"{expected['load']:#x}"
                )
                assert st.exec_address == expected["exec"], path_str
                assert st.locked == expected["locked"], (
                    f"{path_str}: locked {st.locked} vs {expected['locked']}"
                )


# ---------------------------------------------------------------------------
# Modification: mkdir
# ---------------------------------------------------------------------------


class TestChmod:
    def test_chmod_adfs_symbolic(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["chmod", str(adfs_image_filepath), "$.Hello", "LWR/R"]
        )
        assert result.exit_code == 0
        # Verify the access changed.
        result = runner.invoke(cli, ["stat", str(adfs_image_filepath), "$.Hello"])
        assert result.exit_code == 0
        assert "L" in result.output

    def test_chmod_adfs_hex(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["chmod", str(adfs_image_filepath), "$.Hello", "0x0B"]
        )
        assert result.exit_code == 0

    def test_chmod_dfs_lock(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["chmod", str(dfs_image_filepath), "$.HELLO", "L/"])
        assert result.exit_code == 0

    def test_chmod_star_alias(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["*access", str(adfs_image_filepath), "$.Hello", "WR/"]
        )
        assert result.exit_code == 0


class TestSetGetLoad:
    def test_set_load_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["set-load", str(dfs_image_filepath), "$.HELLO", "0xFF00"]
        )
        assert result.exit_code == 0
        result = runner.invoke(
            cli, ["get-load", str(dfs_image_filepath), "$.HELLO"]
        )
        assert result.exit_code == 0
        assert "0000FF00" in result.output

    def test_set_load_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["set-load", str(adfs_image_filepath), "$.Hello", "0xFFFF1234"]
        )
        assert result.exit_code == 0
        result = runner.invoke(
            cli, ["get-load", str(adfs_image_filepath), "$.Hello"]
        )
        assert result.exit_code == 0
        assert "FFFF1234" in result.output

    def test_get_load_original(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["get-load", str(dfs_image_filepath), "$.HELLO"]
        )
        assert result.exit_code == 0
        assert "00001900" in result.output


class TestSetGetExec:
    def test_set_exec_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["set-exec", str(dfs_image_filepath), "$.HELLO", "0xABCD"]
        )
        assert result.exit_code == 0
        result = runner.invoke(
            cli, ["get-exec", str(dfs_image_filepath), "$.HELLO"]
        )
        assert result.exit_code == 0
        assert "0000ABCD" in result.output

    def test_get_exec_original(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(
            cli, ["get-exec", str(dfs_image_filepath), "$.HELLO"]
        )
        assert result.exit_code == 0
        assert "00008023" in result.output


# ---------------------------------------------------------------------------
# Issue #13 — wildcards, -r, and --dry-run for attribute-mutating commands.
# ---------------------------------------------------------------------------


class TestBulkMutation:
    """chmod, lock, unlock, set-load, set-exec, rm all accept the
    Acorn wildcards and -r / --dry-run flags established by cp in
    10.3.0.  The heavy lifting is shared by a single target-
    enumeration helper so the flag set is uniform.
    """

    def test_chmod_glob_applies_to_every_match(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "chmod",
                str(adfs_image_tree),
                "$.Dir.*",
                "LR/R",
            ],
        )
        assert result.exit_code == 0, result.output
        stat_inside = runner.invoke(
            cli, ["stat", str(adfs_image_tree), "$.Dir.Inside"]
        )
        assert "LR/R" in stat_inside.output

    def test_chmod_recursive_descends(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "chmod",
                "-r",
                str(adfs_image_tree),
                "$.Dir",
                "LR/R",
            ],
        )
        assert result.exit_code == 0, result.output
        # Inside and Sub.Deep should both have the new access.
        for bare in ("$.Dir.Inside", "$.Dir.Sub.Deep"):
            st = runner.invoke(cli, ["stat", str(adfs_image_tree), bare])
            assert "LR/R" in st.output, f"{bare} not chmod'd: {st.output}"

    def test_chmod_dry_run_makes_no_change(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        before = runner.invoke(
            cli, ["stat", str(adfs_image_tree), "$.Root1"]
        ).output
        result = runner.invoke(
            cli,
            [
                "chmod",
                "--dry-run",
                str(adfs_image_tree),
                "$.Root1",
                "LR/R",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "would chmod" in result.output.lower() or "$.Root1" in result.output
        after = runner.invoke(
            cli, ["stat", str(adfs_image_tree), "$.Root1"]
        ).output
        assert before == after

    def test_chmod_glob_no_matches_errors(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            ["chmod", str(adfs_image_tree), "$.Xyz*", "WR/"],
        )
        assert result.exit_code != 0
        assert "no match" in result.output.lower()

    def test_lock_glob(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            ["lock", str(adfs_image_tree), "$.Dir.*"],
        )
        assert result.exit_code == 0, result.output
        st = runner.invoke(
            cli, ["stat", str(adfs_image_tree), "$.Dir.Inside"]
        )
        # Any "L"-bearing attr string indicates the lock took.
        assert "L" in st.output

    def test_unlock_recursive(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        # Lock recursively first.
        assert runner.invoke(
            cli, ["lock", "-r", str(adfs_image_tree), "$.Dir"]
        ).exit_code == 0
        # Now unlock recursively.
        result = runner.invoke(
            cli, ["unlock", "-r", str(adfs_image_tree), "$.Dir"]
        )
        assert result.exit_code == 0, result.output
        # Deeply nested file should be unlocked.
        st = runner.invoke(
            cli, ["stat", str(adfs_image_tree), "$.Dir.Sub.Deep"]
        )
        assert "LR/" not in st.output  # No L in the attr

    def test_set_load_glob_applies_to_files_only(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "set-load",
                "-r",
                str(adfs_image_tree),
                "$.Dir",
                "0xCAFE",
            ],
        )
        assert result.exit_code == 0, result.output
        # Every file descendant should have load_address 0x0000CAFE.
        for bare in ("$.Dir.Inside", "$.Dir.Sub.Deep"):
            st = runner.invoke(cli, ["get-load", str(adfs_image_tree), bare])
            assert "0000CAFE" in st.output, (
                f"{bare} not set: {st.output!r}"
            )

    def test_set_exec_glob(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        result = runner.invoke(
            cli,
            [
                "set-exec",
                str(adfs_image_tree),
                "$.Dir.*",
                "0xBEEF",
            ],
        )
        assert result.exit_code == 0, result.output
        st = runner.invoke(cli, ["get-exec", str(adfs_image_tree), "$.Dir.Inside"])
        assert "0000BEEF" in st.output

    def test_rm_glob(
        self,
        runner: CliRunner,
        dfs_image_many_files: Path,
    ) -> None:
        """``rm '$.He*'`` deletes Hello and Help, leaves Data."""
        result = runner.invoke(
            cli, ["rm", str(dfs_image_many_files), "$.He*"]
        )
        assert result.exit_code == 0, result.output
        listing = runner.invoke(cli, ["ls", str(dfs_image_many_files), "$"])
        assert "HELLO" not in listing.output
        assert "HELP" not in listing.output
        assert "DATA" in listing.output

    def test_rm_recursive_glob(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        """``rm -r '$.Dir'`` empties the Dir subtree."""
        result = runner.invoke(
            cli, ["rm", "-r", str(adfs_image_tree), "$.Dir"]
        )
        assert result.exit_code == 0, result.output
        tree = runner.invoke(cli, ["tree", str(adfs_image_tree)])
        assert "Dir" not in tree.output
        assert "Inside" not in tree.output
        assert "Deep" not in tree.output

    def test_dry_run_set_load_makes_no_change(
        self,
        runner: CliRunner,
        adfs_image_tree: Path,
    ) -> None:
        before = runner.invoke(
            cli, ["get-load", str(adfs_image_tree), "$.Root1"]
        ).output
        result = runner.invoke(
            cli,
            [
                "set-load",
                "--dry-run",
                str(adfs_image_tree),
                "$.Root1",
                "0xDEAD",
            ],
        )
        assert result.exit_code == 0
        assert "would" in result.output.lower() or "$.Root1" in result.output
        after = runner.invoke(
            cli, ["get-load", str(adfs_image_tree), "$.Root1"]
        ).output
        assert before == after


class TestMkdir:
    def test_mkdir_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["mkdir", str(adfs_image_filepath), "$.NewDir"])
        assert result.exit_code == 0

    def test_mkdir_dfs_errors(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["mkdir", str(dfs_image_filepath), "$.Dir"])
        assert result.exit_code != 0
        assert "not supported for DFS" in result.output

    def test_mkdir_p_existing(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["mkdir", "-p", str(adfs_image_filepath), "$.Games"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Whole-image: create
# ---------------------------------------------------------------------------


class TestCreate:
    def test_create_ssd(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "new.ssd"
        result = runner.invoke(cli, ["create", str(out), "--format", "ssd"])
        assert result.exit_code == 0
        assert out.exists()
        assert "Created" in result.output

    def test_create_adfs_l(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "new.adl"
        result = runner.invoke(cli, ["create", str(out), "--format", "adfs-l"])
        assert result.exit_code == 0
        assert out.exists()

    def test_create_adfs_hard_with_mib(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "new.dat"
        result = runner.invoke(
            cli, ["create", str(out), "--format", "adfs-hard", "--capacity", "5MiB"]
        )
        assert result.exit_code == 0
        assert out.exists()
        # 5 MiB = 5,242,880 bytes; image rounds up to whole cylinders.
        assert out.stat().st_size >= 5 * 1024 * 1024

    def test_create_adfs_hard_with_mb(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "new.dat"
        result = runner.invoke(
            cli, ["create", str(out), "--format", "adfs-hard", "--capacity", "5 MB"]
        )
        assert result.exit_code == 0
        assert out.exists()

    def test_create_adfs_hard_bare_bytes(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "new.dat"
        result = runner.invoke(
            cli, ["create", str(out), "--format", "adfs-hard", "--capacity", "1048576"]
        )
        assert result.exit_code == 0
        assert out.exists()

    def test_create_adfs_hard_requires_capacity(self, runner: CliRunner, tmp_path: Path) -> None:
        out = tmp_path / "new.dat"
        result = runner.invoke(cli, ["create", str(out), "--format", "adfs-hard"])
        assert result.exit_code != 0
        assert "capacity" in result.output.lower()


# ---------------------------------------------------------------------------
# Whole-image: compact
# ---------------------------------------------------------------------------


class TestFreemap:
    def test_freemap_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["freemap", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "Free:" in result.output
        assert "#" in result.output or "." in result.output

    def test_freemap_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["freemap", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "Free:" in result.output
        assert "region" in result.output

    def test_freemap_afs(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["freemap", str(afs_image_filepath), "afs:"])
        assert result.exit_code == 0
        assert "Free:" in result.output
        assert "cylinders" in result.output


class TestCompact:
    def test_compact_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["compact", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "Compacted" in result.output

    def test_compact_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["compact", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "Compacted" in result.output


# ---------------------------------------------------------------------------
# AFS-specific commands
# ---------------------------------------------------------------------------


class TestImport:
    def test_import_dfs(
        self, runner: CliRunner, dfs_image_filepath: Path, tmp_path: Path,
    ) -> None:
        # Create a host directory with files.
        src = tmp_path / "import_src"
        src.mkdir()
        (src / "NEW").write_bytes(b"imported file")
        result = runner.invoke(
            cli, ["import", str(dfs_image_filepath), str(src)]
        )
        assert result.exit_code == 0
        # Verify the file was imported.
        result = runner.invoke(cli, ["cat", str(dfs_image_filepath), "$.NEW"])
        assert result.exit_code == 0
        assert b"imported file" in result.output_bytes

    def test_import_adfs_with_subdir(
        self, runner: CliRunner, adfs_image_filepath: Path, tmp_path: Path,
    ) -> None:
        src = tmp_path / "import_src"
        src.mkdir()
        (src / "Docs").mkdir()
        (src / "Docs" / "README").write_bytes(b"readme data")
        result = runner.invoke(
            cli, ["import", str(adfs_image_filepath), str(src)]
        )
        assert result.exit_code == 0
        result = runner.invoke(
            cli, ["cat", str(adfs_image_filepath), "$.Docs.README"]
        )
        assert result.exit_code == 0
        assert b"readme data" in result.output_bytes

    def test_import_verbose(
        self, runner: CliRunner, dfs_image_filepath: Path, tmp_path: Path,
    ) -> None:
        src = tmp_path / "import_src"
        src.mkdir()
        (src / "VER").write_bytes(b"verbose test")
        result = runner.invoke(
            cli, ["import", "-v", str(dfs_image_filepath), str(src)]
        )
        assert result.exit_code == 0


class TestAfsPlan:
    def test_afs_plan_max(self, runner: CliRunner, adfs_no_afs_filepath: Path) -> None:
        # Display mode pins the report titles so the layout is
        # asserted as-is; TSV omits titles by design.
        result = runner.invoke(
            cli, ["afs-plan", "--as", "display", str(adfs_no_afs_filepath)]
        )
        assert result.exit_code == 0
        assert "Disc geometry" in result.output
        assert "cylinders" in result.output
        assert "Proposed AFS partition" in result.output
        assert "disc afs-init" in result.output

    def test_afs_plan_explicit_cylinders(
        self, runner: CliRunner, adfs_no_afs_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli, ["afs-plan", str(adfs_no_afs_filepath), "--cylinders", "10"]
        )
        assert result.exit_code == 0
        assert "10 cylinders" in result.output

    def test_afs_plan_already_partitioned(
        self, runner: CliRunner, afs_image_filepath: Path,
    ) -> None:
        # The existing-partition case now surfaces as a dedicated
        # "Existing AFS partition" report rather than a free-text
        # message; pin --as display to see the title.
        result = runner.invoke(
            cli, ["afs-plan", "--as", "display", str(afs_image_filepath)]
        )
        assert result.exit_code == 0
        assert "Existing AFS partition" in result.output

    def test_afs_plan_too_large(
        self, runner: CliRunner, adfs_no_afs_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli, ["afs-plan", str(adfs_no_afs_filepath), "--cylinders", "9999"]
        )
        assert result.exit_code != 0

    def test_afs_plan_as_json(
        self, runner: CliRunner, adfs_no_afs_filepath: Path,
    ) -> None:
        import json

        result = runner.invoke(
            cli, ["afs-plan", str(adfs_no_afs_filepath), "--as", "json"]
        )
        assert result.exit_code == 0
        doc = json.loads(result.output)
        reports = doc["reports"]
        # One report per section: disc geometry, adfs occupancy, plan.
        # (existing_afs is omitted when no partition is installed.)
        assert "geometry" in reports
        assert "adfs_state" in reports
        assert "plan" in reports
        assert "existing_afs" not in reports
        # Plan contents are in the single row of its transposed table.
        plan_row = reports["plan"]["rows"][0]
        assert plan_row["afs_region"]
        assert plan_row["start_cylinder"]
        assert plan_row["will_compact"] == "not required"
        assert plan_row["suggested_command"].startswith("disc afs-init")

    def test_afs_plan_as_json_already_partitioned(
        self, runner: CliRunner, afs_image_filepath: Path,
    ) -> None:
        import json

        result = runner.invoke(
            cli, ["afs-plan", str(afs_image_filepath), "--as", "json"]
        )
        assert result.exit_code == 0
        doc = json.loads(result.output)
        reports = doc["reports"]
        # When a partition already exists, the existing_afs report
        # shows up and the plan report is suppressed.
        assert "existing_afs" in reports
        assert "plan" not in reports
        assert reports["existing_afs"]["rows"][0]["present"] == "yes"

    def test_afs_plan_rejects_unknown_format(
        self, runner: CliRunner, adfs_no_afs_filepath: Path,
    ) -> None:
        result = runner.invoke(
            cli, ["afs-plan", str(adfs_no_afs_filepath), "--as", "xml"]
        )
        assert result.exit_code != 0


class TestAfsInit:
    def test_afs_init(self, runner: CliRunner, adfs_no_afs_filepath: Path) -> None:
        result = runner.invoke(
            cli,
            [
                "afs-init",
                str(adfs_no_afs_filepath),
                "--disc-name",
                "NewAFS",
                "--cylinders",
                "10",
                "--user",
                "alice",
            ],
        )
        assert result.exit_code == 0
        assert "Initialised" in result.output


class TestAfsUsers:
    def test_afs_users(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["afs-users", str(afs_image_filepath)])
        assert result.exit_code == 0
        assert "Syst" in result.output

    def test_afs_users_json_roundtrip(
        self, runner: CliRunner, afs_image_filepath: Path
    ) -> None:
        """--as json emits a parseable document listing every user."""
        import json as _json

        result = runner.invoke(
            cli, ["afs-users", "--as", "json", str(afs_image_filepath)]
        )
        assert result.exit_code == 0, result.output
        doc = _json.loads(result.output)
        payload = next(iter(doc["reports"].values()))
        users = [row["user"] for row in payload["rows"]]
        assert "Syst" in users
        assert "Boot" in users
        assert "Welcome" in users
        # Syst is the one with the system flag set.
        syst_row = next(r for r in payload["rows"] if r["user"] == "Syst")
        assert syst_row["system"] == "yes"

    def test_afs_users_tsv_columns(
        self, runner: CliRunner, afs_image_filepath: Path
    ) -> None:
        result = runner.invoke(
            cli, ["afs-users", "--as", "tsv", str(afs_image_filepath)]
        )
        assert result.exit_code == 0, result.output
        lines = [ln for ln in result.output.splitlines() if ln]
        # First non-data line is the "# User..." header.
        assert lines[0].startswith("#")
        # Each data line has tab-separated user/system/quota.
        data = [ln for ln in lines if not ln.startswith("#")]
        syst_line = next(ln for ln in data if ln.startswith("Syst"))
        cells = syst_line.split("\t")
        assert len(cells) == 3
        assert cells[0] == "Syst"
        assert cells[1] == "yes"
        assert cells[2].startswith("0x")


class TestAfsUserDel:
    def test_afs_userdel(self, runner: CliRunner, afs_image_with_spare_slot: Path) -> None:
        """Remove a pre-existing user (tombstone the slot)."""
        result = runner.invoke(
            cli,
            [
                "afs-userdel",
                str(afs_image_with_spare_slot),
                "alice",
            ],
        )
        assert result.exit_code == 0
        assert "Removed" in result.output


class TestAfsUserAdd:
    def test_afs_useradd_into_tombstoned_slot(
        self,
        runner: CliRunner,
        afs_image_with_spare_slot: Path,
    ) -> None:
        """Remove a user (tombstone), then add a new one into the freed slot."""
        # Tombstone alice first.
        result = runner.invoke(
            cli,
            [
                "afs-userdel",
                str(afs_image_with_spare_slot),
                "alice",
            ],
        )
        assert result.exit_code == 0

        # Add bob into the freed slot.
        result = runner.invoke(
            cli,
            [
                "afs-useradd",
                str(afs_image_with_spare_slot),
                "bob",
            ],
        )
        assert result.exit_code == 0
        assert "Added" in result.output

        result = runner.invoke(cli, ["afs-users", str(afs_image_with_spare_slot)])
        assert "bob" in result.output


class TestAfsPrefixErrors:
    def test_afs_prefix_on_dfs(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(dfs_image_filepath), "afs:$"])
        assert result.exit_code != 0
        assert "AFS partitions exist only on ADFS" in result.output

    def test_afs_on_disc_without_afs(self, runner: CliRunner, adfs_no_afs_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(adfs_no_afs_filepath), "afs:$"])
        assert result.exit_code != 0
        assert "no AFS partition" in result.output

    def test_dfs_prefix_on_adfs(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(adfs_image_filepath), "dfs:$"])
        assert result.exit_code != 0
        assert "cannot access as DFS" in result.output


# ---------------------------------------------------------------------------
# expand
# ---------------------------------------------------------------------------


class TestExpand:
    """Tests for the ``disc expand`` subcommand."""

    def _make_truncated_ssd(self, tmp_path: Path, num_sectors: int = 136) -> Path:
        """Create a truncated .ssd with a minimal DFS catalogue."""
        from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS

        # Create a full image, then truncate it
        full_filepath = tmp_path / "full.ssd"
        with DFS.create_file(full_filepath, ACORN_DFS_80T_SINGLE_SIDED, title="Trunc"):
            pass
        data = full_filepath.read_bytes()
        truncated_filepath = tmp_path / "truncated.ssd"
        truncated_filepath.write_bytes(data[: num_sectors * 256])
        return truncated_filepath

    def test_expand_truncated_ssd(self, runner: CliRunner, tmp_path: Path) -> None:
        filepath = self._make_truncated_ssd(tmp_path)
        result = runner.invoke(cli, ["expand", str(filepath)])
        assert result.exit_code == 0
        assert filepath.stat().st_size == 204800
        assert "Expanded" in result.output

    def test_expand_with_explicit_format(self, runner: CliRunner, tmp_path: Path) -> None:
        filepath = self._make_truncated_ssd(tmp_path, num_sectors=20)
        result = runner.invoke(cli, ["expand", str(filepath), "--format", "ssd"])
        assert result.exit_code == 0
        assert filepath.stat().st_size == 204800

    def test_expand_full_size_reports_no_change(
        self, runner: CliRunner, dfs_image_filepath: Path
    ) -> None:
        original_size = dfs_image_filepath.stat().st_size
        result = runner.invoke(cli, ["expand", str(dfs_image_filepath)])
        assert result.exit_code == 0
        assert "already" in result.output.lower()
        assert dfs_image_filepath.stat().st_size == original_size

    def test_expand_not_sector_aligned(self, runner: CliRunner, tmp_path: Path) -> None:
        filepath = tmp_path / "bad.ssd"
        filepath.write_bytes(b"\x00" * 257)
        result = runner.invoke(cli, ["expand", str(filepath)])
        assert result.exit_code != 0

    def test_expand_nonexistent_file(self, runner: CliRunner, tmp_path: Path) -> None:
        filepath = tmp_path / "nonexistent.ssd"
        result = runner.invoke(cli, ["expand", str(filepath)])
        assert result.exit_code != 0

    def test_expand_dsd(self, runner: CliRunner, tmp_path: Path) -> None:
        from oaknut.dfs import ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, DFS

        full_filepath = tmp_path / "full.dsd"
        with DFS.create_file(
            full_filepath, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, title="DSD"
        ):
            pass
        data = full_filepath.read_bytes()
        truncated_filepath = tmp_path / "truncated.dsd"
        truncated_filepath.write_bytes(data[:20480])
        result = runner.invoke(cli, ["expand", str(truncated_filepath)])
        assert result.exit_code == 0
        assert truncated_filepath.stat().st_size == 409600
