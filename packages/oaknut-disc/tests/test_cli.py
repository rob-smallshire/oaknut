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
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

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
        result = runner.invoke(cli, ["ls", str(dfs_image_filepath)])
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
        result = runner.invoke(cli, ["ls", str(adfs_image_filepath)])
        assert result.exit_code == 0
        assert "Hello" in result.output
        assert "Games" in result.output
        assert "ADFS" in result.output

    def test_ls_adfs_subdirectory(self, runner: CliRunner, adfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(adfs_image_filepath), "$.Games"])
        assert result.exit_code == 0
        assert "Elite" in result.output

    def test_ls_afs_prefix(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["ls", str(afs_image_filepath), "afs:"])
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

    def test_compact_dfs_errors(self, runner: CliRunner, dfs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["compact", str(dfs_image_filepath)])
        assert result.exit_code != 0
        assert "not supported for DFS" in result.output


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
                "Syst:S",
            ],
        )
        assert result.exit_code == 0
        assert "Initialised" in result.output


class TestAfsUsers:
    def test_afs_users(self, runner: CliRunner, afs_image_filepath: Path) -> None:
        result = runner.invoke(cli, ["afs-users", str(afs_image_filepath)])
        assert result.exit_code == 0
        assert "Syst" in result.output


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
