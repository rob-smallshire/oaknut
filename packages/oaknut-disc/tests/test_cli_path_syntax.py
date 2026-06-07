"""Cross-command smoke tests for the fused IMAGE[:PATH] syntax.

Every refactored command takes a single positional spec::

    disc <cmd> IMAGE:PATH

The image and in-image path are joined by a colon at the first
non-Windows-drive colon; any subsequent colon stays on the in-image
side so the ``adfs:``/``afs:``/``dfs:`` filing-system prefix continues
to scope the operation to the right partition. These tests exercise a
handful of core commands in fused form so a regression in the parser
plumbing trips here, not in the format-specific suites.

The per-command failure-mode tests in ``test_cli_error_reporting``
cover the error categories; the tests here focus on the parser
contract.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli

# ---------------------------------------------------------------------------
# Single-image, single-path commands
# ---------------------------------------------------------------------------


class TestSingleImageSinglePath:
    """ls / stat / cat / get-load / mkdir in fused form."""

    def test_ls_fused_with_path(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["ls", f"{adfs_image_filepath}:$.Games"])
        assert result.exit_code == 0, result.output

    def test_ls_fused_no_path(self, runner: CliRunner, adfs_image_filepath: Path):
        # "image:" with no in-image part is equivalent to a bare image.
        bare = runner.invoke(cli, ["ls", str(adfs_image_filepath)])
        fused_empty = runner.invoke(cli, ["ls", f"{adfs_image_filepath}:"])
        assert bare.exit_code == 0
        assert fused_empty.exit_code == 0
        assert bare.output == fused_empty.output

    def test_stat_fused(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["stat", f"{adfs_image_filepath}:$.Hello"])
        assert result.exit_code == 0, result.output

    def test_cat_fused(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["cat", f"{adfs_image_filepath}:$.Hello"])
        assert result.exit_code == 0, result.output

    def test_get_load_fused(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli, ["get-load", "--as", "display", f"{adfs_image_filepath}:$.Hello"]
        )
        assert result.exit_code == 0, result.output
        # The fixture writes Hello with load=0x1900 (hex for humans).
        assert "0x00001900" in result.output

    def test_mkdir_fused(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["mkdir", f"{adfs_image_filepath}:$.Fused"])
        assert result.exit_code == 0, result.output
        ls = runner.invoke(cli, ["ls", str(adfs_image_filepath)])
        assert "Fused" in ls.output


# ---------------------------------------------------------------------------
# Commands with a trailing arg after the path
# ---------------------------------------------------------------------------


class TestImagePathTrailing:
    """chmod / set-load / get -- fused IMAGE:PATH plus a trailing arg."""

    def test_chmod_fused(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["chmod", f"{adfs_image_filepath}:$.Hello", "WR/R"])
        assert result.exit_code == 0, result.output

    def test_set_load_fused_roundtrips(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["set-load", f"{adfs_image_filepath}:$.Hello", "0x3B00"])
        assert result.exit_code == 0, result.output
        gl = runner.invoke(cli, ["get-load", "--as", "display", f"{adfs_image_filepath}:$.Hello"])
        assert "0x00003B00" in gl.output

    def test_get_fused(
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
    def test_fused_single_path(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(cli, ["rm", f"{adfs_image_filepath}:$.Hello"])
        assert result.exit_code == 0, result.output

    def test_fused_with_extra_paths(self, runner: CliRunner, adfs_image_filepath: Path):
        # rm image:$.Hello $.Games -r  -- fused first path plus extra
        # bare in-image paths.
        result = runner.invoke(
            cli,
            ["rm", "-r", f"{adfs_image_filepath}:$.Hello", "$.Games"],
        )
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Two-image: cp
# ---------------------------------------------------------------------------


class TestCpPathSyntax:
    def test_two_fused_args(
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


# ---------------------------------------------------------------------------
# Two-arg: mv
# ---------------------------------------------------------------------------


class TestMvPathSyntax:
    def test_two_fused_args(self, runner: CliRunner, adfs_image_filepath: Path):
        result = runner.invoke(
            cli,
            [
                "mv",
                f"{adfs_image_filepath}:$.Hello",
                f"{adfs_image_filepath}:$.Greeting",
            ],
        )
        assert result.exit_code == 0, result.output

    def test_two_fused_cross_image_rejected(
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

    def test_bare_inner_destination(self, runner: CliRunner, adfs_image_filepath: Path):
        # The destination's image is redundant (mv is single-image), so a
        # bare in-image path is accepted and inherits the source's image,
        # mirroring rm's trailing-path form.
        result = runner.invoke(
            cli,
            ["mv", f"{adfs_image_filepath}:$.Hello", "$.Greeting"],
        )
        assert result.exit_code == 0, result.output

        listing = runner.invoke(cli, ["ls", f"{adfs_image_filepath}:$"])
        assert "Greeting" in listing.output
        assert "Hello" not in listing.output


class TestMvPartitionScoping:
    """A partition selector on the destination must not contradict the
    source; mv never moves across partitions."""

    def test_bare_inner_inherits_source_partition(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        # Rename the last entry so the directory stays sorted (ADFS
        # rename does not re-sort).
        result = runner.invoke(
            cli,
            ["mv", f"{partitioned_image_with_files}:adfs:adfsB", "adfsZ"],
        )
        assert result.exit_code == 0, result.output

        listing = runner.invoke(cli, ["ls", f"{partitioned_image_with_files}:adfs:$"])
        assert "adfsZ" in listing.output
        assert "adfsB" not in listing.output

    def test_matching_destination_selector_allowed(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        result = runner.invoke(
            cli,
            ["mv", f"{partitioned_image_with_files}:adfs:adfsB", "adfs:adfsZ"],
        )
        assert result.exit_code == 0, result.output

    def test_conflicting_destination_selector_rejected(
        self, runner: CliRunner, partitioned_image_with_files: Path
    ):
        result = runner.invoke(
            cli,
            ["mv", f"{partitioned_image_with_files}:adfs:adfsA", "afs:moved"],
        )
        assert result.exit_code != 0
        assert "partition" in result.output


# ---------------------------------------------------------------------------
# Filing-system prefix passes through the fused form
# ---------------------------------------------------------------------------


class TestFsPrefixWithFusedForm:
    """The adfs:/afs:/dfs: filing-system prefix sits on the in-image
    side of the outer image-colon. It must route through resolve_path
    so the prefix scopes the operation to the right partition.
    """

    def test_afs_prefix_fused(
        self,
        runner: CliRunner,
        partitioned_image_with_files: Path,
    ):
        result = runner.invoke(
            cli,
            ["ls", f"{partitioned_image_with_files}:afs:$"],
        )
        assert result.exit_code == 0, result.output
        # AFS partition has GAMES + afsA per the fixture.
        assert "GAMES" in result.output or "afsA" in result.output

    def test_adfs_prefix_fused(
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
