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


def _protected_hfe(tmp_path):
    """A two-track FM disc whose second track carries protection tricks."""
    from oaknut.hfe.build import FormattedSector, build_track, track_samples
    from oaknut.hfe.container import write_hfe
    from oaknut.hfe.decode import Encoding, SectorID

    def fm(sectors):
        return track_samples(build_track(sectors, Encoding.FM, half_cells=50_000), Encoding.FM)

    standard = [FormattedSector(SectorID(0, 0, r, 1), bytes([r]) * 256) for r in range(10)]
    tricks = [FormattedSector(SectorID(1, 0, r, 1), b"ok") for r in range(8)] + [
        FormattedSector(SectorID(1, 0, 8, 1), b"bad", bad_data_crc=True),
        FormattedSector(SectorID(0x20, 0, 9, 1), b"decoy", deleted=True),
    ]
    filepath = tmp_path / "protected.hfe"
    filepath.write_bytes(write_hfe([[fm(standard)], [fm(tricks)]]))
    return filepath


class TestHfeInfo:
    def test_header_and_layout(self, runner: CliRunner):
        result = runner.invoke(cli, ["hfe", "info", "--as", "json", S1_HFE])
        assert result.exit_code == 0, result.output
        assert '"ISOIBM_FM"' in result.output
        assert '"tracks": 41' in result.output
        assert '"tracks": 40' in result.output


class TestHfeSectors:
    def test_dunjunz_anomalies_are_only_its_blank_track(self, runner: CliRunner):
        result = runner.invoke(cli, ["hfe", "sectors", "--anomalies", "--report", "tracks", S1_HFE])
        assert result.exit_code == 0, result.output
        rows = [line for line in result.output.splitlines() if not line.startswith("#")]
        assert rows == ["40\t0\t0\t0\tunformatted"]

    def test_one_track(self, runner: CliRunner):
        result = runner.invoke(
            cli, ["hfe", "sectors", "--track", "3", "--report", "sectors", S1_HFE]
        )
        rows = [line.split("\t") for line in result.output.splitlines() if not line.startswith("#")]
        assert len(rows) == 10
        assert {row[0] for row in rows} == {"3"}

    def test_protection_is_remarked(self, runner: CliRunner, tmp_path):
        image = str(_protected_hfe(tmp_path))
        result = runner.invoke(cli, ["hfe", "sectors", "--anomalies", "--report", "sectors", image])
        assert result.exit_code == 0, result.output
        assert "data CRC error" in result.output
        assert "deleted data; cylinder 32 on track 1" in result.output
        tracks = runner.invoke(cli, ["hfe", "sectors", "--anomalies", "--report", "tracks", image])
        assert "9 of 10 sectors; missing records 9" in tracks.output


class TestHfeFlatten:
    def test_matches_the_golden_ssd(self, runner: CliRunner, tmp_path):
        output = tmp_path / "out.ssd"
        result = runner.invoke(cli, ["hfe", "flatten", S2_HFE, str(output)])
        assert result.exit_code == 0, result.output
        assert output.read_bytes() == (HFE_DIRPATH / f"{S2_STEM}.ssd").read_bytes()

    def test_refuses_to_overwrite_without_force(self, runner: CliRunner, tmp_path):
        output = tmp_path / "out.ssd"
        output.write_bytes(b"keep")
        refused = runner.invoke(cli, ["hfe", "flatten", S2_HFE, str(output)])
        assert refused.exit_code != 0
        assert output.read_bytes() == b"keep"
        forced = runner.invoke(cli, ["hfe", "flatten", "--force", S2_HFE, str(output)])
        assert forced.exit_code == 0, forced.output
        assert len(output.read_bytes()) == 102_400

    def test_unreadable_sectors_get_the_fill_byte(self, runner: CliRunner, tmp_path):
        output = tmp_path / "out.ssd"
        image = str(_protected_hfe(tmp_path))
        result = runner.invoke(cli, ["hfe", "flatten", "--fill", "0xE5", image, str(output)])
        assert result.exit_code == 0, result.output
        data = output.read_bytes()
        assert data[2560 + 8 * 256 : 2560 + 10 * 256] == b"\xe5" * 512
        assert "2 sector(s) unreadable" in result.stderr

    def test_notes_an_unconventional_extension(self, runner: CliRunner, tmp_path):
        result = runner.invoke(cli, ["hfe", "flatten", S2_HFE, str(tmp_path / "out.img")])
        assert result.exit_code == 0
        assert ".ssd" in result.stderr

    def test_rejects_a_fill_that_is_not_a_byte(self, runner: CliRunner, tmp_path):
        result = runner.invoke(
            cli, ["hfe", "flatten", "--fill", "300", S2_HFE, str(tmp_path / "o")]
        )
        assert result.exit_code != 0
