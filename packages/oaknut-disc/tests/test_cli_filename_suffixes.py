"""Filename-suffix metadata formats across the host boundary.

``filename-riscos`` writes ``,xxx`` for a filetyped file and the
``,load-exec`` form RISC OS LanManFS and HostFS read for an untyped
one; ``filename-loadexec`` writes ``,load-exec`` for every file. The
old ``filename-mos`` name still works, with a deprecation warning.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args):
    return runner.invoke(cli, list(args))


def _dfs_with_prog(runner, tmp_path: Path) -> Path:
    image = tmp_path / "d.ssd"
    _run(runner, "create", str(image), "--title", "T")
    host = tmp_path / "payload"
    host.write_bytes(b"data")
    r = _run(
        runner,
        "put",
        f"{image}:$.PROG",
        str(host),
        "--meta-format",
        "none",
        "--load",
        "0x1900",
        "--exec",
        "0x8023",
    )
    assert r.exit_code == 0, r.output
    return image


class TestGet:
    def test_filename_riscos_writes_load_exec(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_prog(runner, tmp_path)
        r = _run(
            runner,
            "get",
            f"{image}:$.PROG",
            str(tmp_path / "PROG"),
            "--meta-format",
            "filename-riscos",
        )
        assert r.exit_code == 0, r.output
        assert (tmp_path / "PROG,1900-8023").read_bytes() == b"data"

    def test_filename_loadexec_writes_load_exec(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_prog(runner, tmp_path)
        r = _run(
            runner,
            "get",
            f"{image}:$.PROG",
            str(tmp_path / "PROG"),
            "--meta-format",
            "filename-loadexec",
        )
        assert r.exit_code == 0, r.output
        assert (tmp_path / "PROG,1900-8023").is_file()

    def test_filename_mos_is_deprecated(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_prog(runner, tmp_path)
        r = _run(
            runner,
            "get",
            f"{image}:$.PROG",
            str(tmp_path / "PROG"),
            "--meta-format",
            "filename-mos",
        )
        assert r.exit_code == 0, r.output
        assert "deprecated" in r.stderr
        assert (tmp_path / "PROG,1900-8023").is_file()


class TestPut:
    def test_reads_fixed_width_comma_form(self, runner: CliRunner, tmp_path: Path):
        """Files exported under the earlier filename-riscos still import."""
        image = tmp_path / "d.ssd"
        _run(runner, "create", str(image), "--title", "T")
        host = tmp_path / "PROG,00001900,00008023"
        host.write_bytes(b"data")
        r = _run(runner, "put", f"{image}:$.PROG", str(host))
        assert r.exit_code == 0, r.output
        r = _run(runner, "get-load", f"{image}:$.PROG")
        assert r.output.strip() == str(0x1900)


def _dfs_with_io_processor_prog(runner, tmp_path: Path) -> Path:
    image = tmp_path / "io.ssd"
    _run(runner, "create", str(image), "--title", "T")
    host = tmp_path / "payload"
    host.write_bytes(b"data")
    r = _run(
        runner,
        "put",
        f"{image}:$.PROG",
        str(host),
        "--meta-format",
        "none",
        "--load",
        "0xFFFF1900",
        "--exec",
        "0xFFFF8023",
    )
    assert r.exit_code == 0, r.output
    return image


class TestMetadataLens:
    """filename-riscos writes ,xxx only under the type-date lens."""

    def test_get_keeps_io_processor_address_on_dfs(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_io_processor_prog(runner, tmp_path)
        r = _run(
            runner,
            "get",
            f"{image}:$.PROG",
            str(tmp_path / "PROG"),
            "--meta-format",
            "filename-riscos",
        )
        assert r.exit_code == 0, r.output
        assert (tmp_path / "PROG,ffff1900-ffff8023").is_file()

    def test_get_type_date_lens_writes_filetype(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_io_processor_prog(runner, tmp_path)
        r = _run(
            runner,
            "get",
            f"{image}:$.PROG",
            str(tmp_path / "PROG"),
            "--meta-format",
            "filename-riscos",
            "--metadata-lens",
            "type-date",
        )
        assert r.exit_code == 0, r.output
        assert (tmp_path / "PROG,f19").is_file()

    def test_export_keeps_io_processor_address_on_dfs(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_io_processor_prog(runner, tmp_path)
        out_dirpath = tmp_path / "out"
        out_dirpath.mkdir()
        r = _run(runner, "export", str(image), str(out_dirpath), "--meta-format", "filename-riscos")
        assert r.exit_code == 0, r.output
        assert [p.name for p in out_dirpath.rglob("PROG*")] == ["PROG,ffff1900-ffff8023"]

    def test_export_type_date_lens_writes_filetype(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_io_processor_prog(runner, tmp_path)
        out_dirpath = tmp_path / "out"
        out_dirpath.mkdir()
        r = _run(
            runner,
            "export",
            str(image),
            str(out_dirpath),
            "--meta-format",
            "filename-riscos",
            "--metadata-lens",
            "type-date",
        )
        assert r.exit_code == 0, r.output
        assert [p.name for p in out_dirpath.rglob("PROG*")] == ["PROG,f19"]
