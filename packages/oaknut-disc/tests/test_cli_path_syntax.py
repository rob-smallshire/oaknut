"""Cross-command tests for the unified IMAGE_SPEC [PATH] syntax.

Every refactored command accepts two equivalent shapes::

    disc <cmd> IMAGE PATH         # split form
    disc <cmd> IMAGE:PATH         # fused form

These tests exercise both forms on every command class and prove that
the ``adfs:``/``afs:``/``dfs:`` filing-system prefix continues to
work in both shapes (since the outer image-colon split happens at the
*first* non-Windows-drive colon, any subsequent colon stays on the
in-image side).

The per-command failure-mode tests in ``test_cli_error_reporting``
already cover error categories; the tests here focus on the parser
contract -- that both shapes route through to the same library
operation with the same result.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner
from oaknut.disc.cli import cli

# ---------------------------------------------------------------------------
# Single-image, single-path commands
# ---------------------------------------------------------------------------


class TestSingleImageSinglePath:
    """ls / tree / stat / cat / type / find / freemap / get-load / get-exec / mkdir / lock / unlock.

    Each test invokes the same logical operation in both forms and
    asserts the result is the same. The shape "both succeed" matters
    more than the exact output, so the assertions stay loose.
    """

    @pytest.mark.parametrize(
        "command, path",
        [
            # ls and stat can target a file or directory; tree wants
            # a directory; cat wants a file.
            ("ls", "$.Hello"),
            ("ls", "$.Games"),
            ("tree", "$.Games"),
            ("stat", "$.Hello"),
            ("stat", "$.Games"),
            ("cat", "$.Hello"),
        ],
    )
    def test_both_forms_succeed_on_existing_path(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        command: str,
        path: str,
    ):
        split_result = runner.invoke(cli, [command, str(adfs_image_filepath), path])
        fused_result = runner.invoke(cli, [command, f"{adfs_image_filepath}:{path}"])
        assert split_result.exit_code == 0, split_result.output
        assert fused_result.exit_code == 0, fused_result.output

    def test_ls_directory_both_forms(self, runner: CliRunner, adfs_image_filepath: Path):
        split = runner.invoke(cli, ["ls", str(adfs_image_filepath), "$.Games"])
        fused = runner.invoke(cli, ["ls", f"{adfs_image_filepath}:$.Games"])
        assert split.exit_code == 0
        assert fused.exit_code == 0
        # Same TSV output (no rendering differences between forms).
        assert split.output == fused.output

    def test_ls_no_path_both_forms(self, runner: CliRunner, adfs_image_filepath: Path):
        # "image" and "image:" both mean "list the root directory".
        split = runner.invoke(cli, ["ls", str(adfs_image_filepath)])
        fused = runner.invoke(cli, ["ls", f"{adfs_image_filepath}:"])
        assert split.exit_code == 0
        assert fused.exit_code == 0
        assert split.output == fused.output

    def test_get_load_both_forms(self, runner: CliRunner, adfs_image_filepath: Path):
        split = runner.invoke(cli, ["get-load", str(adfs_image_filepath), "$.Hello"])
        fused = runner.invoke(cli, ["get-load", f"{adfs_image_filepath}:$.Hello"])
        assert split.exit_code == 0
        assert fused.exit_code == 0
        # The fixture writes Hello with load=0x1900.
        assert "1900" in split.output.lower() or "1900" in split.output
        assert split.output == fused.output

    def test_mkdir_both_forms(self, runner: CliRunner, adfs_image_filepath: Path):
        split = runner.invoke(cli, ["mkdir", str(adfs_image_filepath), "$.Split"])
        assert split.exit_code == 0, split.output
        fused = runner.invoke(cli, ["mkdir", f"{adfs_image_filepath}:$.Fused"])
        assert fused.exit_code == 0, fused.output
        # Both directories should now exist.
        ls = runner.invoke(cli, ["ls", str(adfs_image_filepath)])
        assert "Split" in ls.output
        assert "Fused" in ls.output


# ---------------------------------------------------------------------------
# Commands with a trailing arg after the path
# ---------------------------------------------------------------------------


class TestImagePathTrailing:
    """chmod / set-load / set-exec / get / put -- the helper-based dispatch."""

    def test_chmod_split_form(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            ["chmod", str(adfs_image_filepath), "$.Hello", "WR/R"],
        )
        assert result.exit_code == 0, result.output

    def test_chmod_fused_form(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["chmod", f"{adfs_image_filepath}:$.Hello", "WR/R"])
        assert result.exit_code == 0, result.output

    def test_set_load_split_form(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            ["set-load", str(adfs_image_filepath), "$.Hello", "0x2A00"],
        )
        assert result.exit_code == 0, result.output
        # Verify it stuck.
        gl = runner.invoke(cli, ["get-load", str(adfs_image_filepath), "$.Hello"])
        assert "2A00" in gl.output

    def test_set_load_fused_form(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["set-load", f"{adfs_image_filepath}:$.Hello", "0x3B00"])
        assert result.exit_code == 0, result.output
        gl = runner.invoke(cli, ["get-load", f"{adfs_image_filepath}:$.Hello"])
        assert "3B00" in gl.output

    def test_get_split_form(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        tmp_path: Path,
    ):
        out_filepath = tmp_path / "out_split"
        result = runner.invoke(
            cli,
            ["get", str(adfs_image_filepath), "$.Hello", str(out_filepath)],
        )
        assert result.exit_code == 0, result.output
        assert out_filepath.exists()
        assert out_filepath.read_bytes() == b"Hello ADFS"

    def test_get_fused_form(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        tmp_path: Path,
    ):
        out_filepath = tmp_path / "out_fused"
        result = runner.invoke(
            cli,
            ["get", f"{adfs_image_filepath}:$.Hello", str(out_filepath)],
        )
        assert result.exit_code == 0, result.output
        assert out_filepath.exists()
        assert out_filepath.read_bytes() == b"Hello ADFS"


# ---------------------------------------------------------------------------
# Multi-path: rm
# ---------------------------------------------------------------------------


class TestRmPathSyntax:
    def test_split_form_two_paths(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
    ):
        # adfs_image_filepath fixture has $.Hello and $.Games/Elite;
        # delete both with split-form syntax.
        result = runner.invoke(
            cli,
            ["rm", "-r", str(adfs_image_filepath), "$.Hello", "$.Games"],
        )
        assert result.exit_code == 0, result.output

    def test_fused_form_single_path(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
    ):
        result = runner.invoke(cli, ["rm", f"{adfs_image_filepath}:$.Hello"])
        assert result.exit_code == 0, result.output

    def test_fused_form_with_extra_paths(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
    ):
        # rm image:$.Hello $.Games -r  -- fused first path plus extra.
        result = runner.invoke(
            cli,
            [
                "rm",
                "-r",
                f"{adfs_image_filepath}:$.Hello",
                "$.Games",
            ],
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Two-image: cp
# ---------------------------------------------------------------------------


class TestCpPathSyntax:
    def test_two_arg_fused_form(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        adfs_empty_filepath: Path,
    ):
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_filepath}:$.Hello",
                f"{adfs_empty_filepath}:$.Hello",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_three_arg_same_image_form(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
    ):
        # Same-image cp using the legacy 3-arg shape.
        result = runner.invoke(
            cli,
            ["cp", str(adfs_image_filepath), "$.Hello", "$.HelloCopy"],
        )
        assert result.exit_code == 0, result.output

    def test_four_arg_cross_image_split_form(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        adfs_empty_filepath: Path,
    ):
        # New 4-arg shape: SRC_IMAGE SRC DST_IMAGE DST -- cross-image,
        # both halves split.
        result = runner.invoke(
            cli,
            [
                "cp",
                str(adfs_image_filepath),
                "$.Hello",
                str(adfs_empty_filepath),
                "$.Hello",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_two_arg_mixed_forms_rejected(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        adfs_empty_filepath: Path,
    ):
        # If only one of two args is fused, that's an ambiguous shape;
        # the parser rejects it with a UsageError.
        result = runner.invoke(
            cli,
            [
                "cp",
                f"{adfs_image_filepath}:$.Hello",
                str(adfs_empty_filepath),
            ],
        )
        assert result.exit_code != 0
        assert "image:path form" in result.output


# ---------------------------------------------------------------------------
# Two-arg: mv
# ---------------------------------------------------------------------------


class TestMvPathSyntax:
    def test_three_arg_split_form(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            ["mv", str(adfs_image_filepath), "$.Hello", "$.Greeting"],
        )
        assert result.exit_code == 0, result.output

    def test_two_arg_fused_form(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            [
                "mv",
                f"{adfs_image_filepath}:$.Hello",
                f"{adfs_image_filepath}:$.Greeting",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_two_arg_cross_image_rejected(
        self,
        runner: CliRunner,
        adfs_image_filepath: Path,
        adfs_empty_filepath: Path,
    ):
        # mv is single-image; cross-image fused form must be rejected.
        result = runner.invoke(
            cli,
            [
                "mv",
                f"{adfs_image_filepath}:$.Hello",
                f"{adfs_empty_filepath}:$.Hello",
            ],
        )
        assert result.exit_code != 0
        assert "same image" in result.output


# ---------------------------------------------------------------------------
# Filing-system prefix passes through both forms
# ---------------------------------------------------------------------------


class TestFsPrefixWithBothForms:
    """The adfs:/afs:/dfs: filing-system prefix sits on the in-image
    side of the outer image-colon. Both fused and split forms must
    route through resolve_path the same way so the prefix scopes the
    operation to the right partition.
    """

    def test_afs_prefix_split_form(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ):
        result = runner.invoke(
            cli,
            ["ls", str(partitioned_image_with_files), "afs:$"],
        )
        assert result.exit_code == 0, result.output
        # AFS partition has GAMES + afsA per the fixture.
        assert "GAMES" in result.output or "afsA" in result.output

    def test_afs_prefix_fused_form(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ):
        result = runner.invoke(
            cli,
            ["ls", f"{partitioned_image_with_files}:afs:$"],
        )
        assert result.exit_code == 0, result.output
        # Should be the SAME output as the split form -- both end up
        # in resolve_path with the same args.
        split = runner.invoke(
            cli,
            ["ls", str(partitioned_image_with_files), "afs:$"],
        )
        assert result.output == split.output

    def test_adfs_prefix_fused_form(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ):
        result = runner.invoke(
            cli,
            ["ls", f"{partitioned_image_with_files}:adfs:$"],
        )
        assert result.exit_code == 0, result.output
        # ADFS partition has adfsA + adfsB per the fixture.
        assert "adfsA" in result.output or "adfsB" in result.output


# ---------------------------------------------------------------------------
# Negative cases the parser must catch
# ---------------------------------------------------------------------------


class TestParserNegativeCases:
    def test_fused_plus_extra_path_rejected(self, runner: CliRunner, adfs_image_filepath: Path):
        # ls image:path path -- supplying both fused form AND a
        # separate PATH should fail with a UsageError, not silently
        # drop one.
        result = runner.invoke(
            cli,
            ["ls", f"{adfs_image_filepath}:$.Games", "$.Hello"],
        )
        assert result.exit_code != 0
        assert "must not be given" in result.output

    def test_fused_with_nonexistent_image_quotes_lhs(self, runner: CliRunner, tmp_path: Path):
        # When the LHS of a fused spec doesn't exist, the error should
        # quote only the LHS portion -- not the whole string -- so the
        # user immediately sees what was looked up.
        missing = tmp_path / "no_such.adl"
        result = runner.invoke(cli, ["ls", f"{missing}:$.Games"])
        assert result.exit_code != 0
        assert "image not found" in result.output
        assert "no_such.adl" in result.output
        # The in-image portion must NOT appear in the error message.
        assert "$.Games" not in result.output
