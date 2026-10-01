"""INF names travel in each filing system's own name codec (#72).

On DFS the ``acorn`` codec stores ``£`` as byte &60, so a traditional
``.inf`` sidecar written from a DFS image carries that catalogue byte,
and a sidecar read into a DFS image decodes it back to ``£``.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args):
    return runner.invoke(cli, list(args))


def _names(runner, image: Path) -> set[str]:
    out = _run(runner, "ls", "--as", "tsv", f"{image}:$").output
    rows = [r for r in out.splitlines() if r and not r.startswith("#")]
    return {r.split("\t")[0] for r in rows}


def _dfs_with_pound_file(runner, tmp_path: Path) -> Path:
    image = tmp_path / "d.ssd"
    _run(runner, "create", str(image), "--title", "T")
    host = tmp_path / "payload"
    host.write_bytes(b"data")
    r = _run(runner, "put", f"{image}:$.COST£", str(host), "--meta-format", "none")
    assert r.exit_code == 0, r.output
    return image


class TestExport:
    def test_get_writes_the_catalogue_byte(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_pound_file(runner, tmp_path)
        out = tmp_path / "COST"
        r = _run(runner, "get", f"{image}:$.COST£", str(out))
        assert r.exit_code == 0, r.output
        assert (tmp_path / "COST.inf").read_bytes().startswith(b"COST` ")

    def test_export_writes_the_catalogue_byte(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_pound_file(runner, tmp_path)
        out_dirpath = tmp_path / "out"
        out_dirpath.mkdir()
        r = _run(runner, "export", str(image), str(out_dirpath))
        assert r.exit_code == 0, r.output
        sidecars = list(out_dirpath.rglob("*.inf"))
        assert len(sidecars) == 1
        assert b"COST` " in sidecars[0].read_bytes()


class TestImport:
    def _host_file(self, tmp_path: Path) -> Path:
        src_dirpath = tmp_path / "src"
        src_dirpath.mkdir()
        host = src_dirpath / "COST"
        host.write_bytes(b"data")
        (src_dirpath / "COST.inf").write_bytes(b"$.COST` 00001900 00008023 00000004 33\n")
        return host

    def test_put_decodes_the_catalogue_byte(self, runner: CliRunner, tmp_path: Path):
        host = self._host_file(tmp_path)
        image = tmp_path / "d.ssd"
        _run(runner, "create", str(image), "--title", "T")
        r = _run(runner, "put", f"{image}:$", str(host))
        assert r.exit_code == 0, r.output
        assert "COST£" in _names(runner, image)

    def test_import_decodes_the_catalogue_byte(self, runner: CliRunner, tmp_path: Path):
        host = self._host_file(tmp_path)
        image = tmp_path / "d.ssd"
        _run(runner, "create", str(image), "--title", "T")
        r = _run(runner, "import", str(image), str(host.parent))
        assert r.exit_code == 0, r.output
        assert "COST£" in _names(runner, image)

    def test_round_trip(self, runner: CliRunner, tmp_path: Path):
        image = _dfs_with_pound_file(runner, tmp_path)
        out_dirpath = tmp_path / "out"
        out_dirpath.mkdir()
        _run(runner, "export", str(image), str(out_dirpath))
        copy = tmp_path / "copy.ssd"
        _run(runner, "create", str(copy), "--title", "T")
        r = _run(runner, "import", str(copy), str(out_dirpath))
        assert r.exit_code == 0, r.output
        assert "COST£" in _names(runner, copy)
