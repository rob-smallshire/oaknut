"""End-to-end `disc` CLI coverage for HFE flux images."""

from __future__ import annotations

from click.testing import CliRunner
from oaknut.disc.cli import cli

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

HFE_DIRPATH = REFERENCE_IMAGES_DIRPATH / "hfe"
S1_STEM = "Dunjunz_D1S1_40T_HG3_8518BF40_1"
S2_STEM = "Dunjunz_D1S2_40T_HG3_54F4B47A_1"
S1_HFE = str(HFE_DIRPATH / f"{S1_STEM}.hfe")
S2_HFE = str(HFE_DIRPATH / f"{S2_STEM}.hfe")


class TestGenericCommands:
    def test_ls(self, runner: CliRunner):
        result = runner.invoke(cli, ["ls", f"{S1_HFE}:$"])
        assert result.exit_code == 0, result.output
        for name in ("README", "!BOOT", "Dunjunz", "Level1"):
            assert name in result.output

    def test_get_load_and_exec(self, runner: CliRunner):
        load = runner.invoke(cli, ["get-load", f"{S2_HFE}:$.Dunjunz"])
        exec_ = runner.invoke(cli, ["get-exec", f"{S2_HFE}:$.Dunjunz"])
        assert load.exit_code == 0, load.output
        # Machine output (the CliRunner default) is decimal.
        assert int(load.output) == 0x26C0
        assert int(exec_.output) == 0x2700

    def test_cat_matches_the_golden_ssd(self, runner: CliRunner):
        from_hfe = runner.invoke(cli, ["cat", f"{S1_HFE}:$.Code2"])
        from_ssd = runner.invoke(cli, ["cat", f"{HFE_DIRPATH / S1_STEM}.ssd:$.Code2"])
        assert from_hfe.exit_code == 0, from_hfe.output
        assert len(from_hfe.stdout_bytes) == 0x105A
        assert from_hfe.stdout_bytes == from_ssd.stdout_bytes

    def test_export(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["export", S2_HFE, str(tmp_path / "out")])
        assert result.exit_code == 0, result.output
        exported = {p.name for p in (tmp_path / "out").rglob("*") if p.is_file()}
        assert any(name.startswith("Level24") for name in exported)

    def test_stat_sees_the_catalogue_not_the_capture(self, runner: CliRunner):
        result = runner.invoke(cli, ["stat", S1_HFE])
        assert result.exit_code == 0, result.output
        assert "MASTER 128 V" in result.output

    def test_identify(self, runner: CliRunner):
        result = runner.invoke(cli, ["identify", "--as", "display", S1_HFE])
        assert result.exit_code == 0, result.output
        assert "acorn-dfs" in result.output
        assert "decoded from HFE v3" in result.output


class TestReadOnly:
    def test_put_is_refused(self, runner: CliRunner, tmp_path):
        payload = tmp_path / "data.bin"
        payload.write_bytes(b"x")
        result = runner.invoke(cli, ["put", f"{S1_HFE}:$.NEW", str(payload)])
        assert result.exit_code != 0
        assert "read-only" in result.output
