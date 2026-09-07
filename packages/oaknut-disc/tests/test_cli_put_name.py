"""`put` in-image naming: --name, sidecar name, host name, and dir dests.

Priority for the in-image leaf: --name > an explicit file-dest leaf >
the sidecar's Acorn name > the host filename. A destination that names a
directory (the root $, or an existing directory) derives the leaf from
that ladder; a destination that names a file uses that name.

All fixtures are built from scratch — analogues, not any external file.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner
from oaknut.disc.cli import cli


def _run(runner, *args, **kw):
    return runner.invoke(cli, list(args), **kw)


def _host_file_with_inf(tmp_path: Path, host_name: str, inf_name: str) -> Path:
    """A host data file plus a traditional INF naming a different Acorn name."""
    data = tmp_path / host_name
    data.write_bytes(b"payload!!" * 4)
    (tmp_path / f"{host_name}.inf").write_text(
        f"{inf_name}    00000800 0000B82B 00000020 WR\n"
    )
    return data


def _names(runner, image: Path) -> set[str]:
    out = _run(runner, "ls", "--as", "tsv", f"{image}:$").output
    rows = [r for r in out.splitlines() if r and not r.startswith("#")]
    return {r.split("\t")[0] for r in rows}


def _make_dfs(runner, tmp_path: Path) -> Path:
    image = tmp_path / "d.ssd"
    _run(runner, "create", str(image), "--title", "T")
    return image


class TestDirectoryDestDerivesLeaf:
    def test_root_dest_uses_sidecar_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host = _host_file_with_inf(tmp_path, "test8_3", "test8/3")
        r = _run(runner, "put", f"{image}:$", str(host), "--meta-format", "inf-trad")
        assert r.exit_code == 0, r.output
        assert "test8/3" in _names(runner, image)

    def test_root_dest_falls_back_to_host_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host = tmp_path / "PLAIN"
        host.write_bytes(b"data")
        r = _run(runner, "put", f"{image}:$", str(host))
        assert r.exit_code == 0, r.output
        assert "PLAIN" in _names(runner, image)

    def test_name_option_overrides_sidecar(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host = _host_file_with_inf(tmp_path, "test8_3", "test8/3")
        r = _run(
            runner, "put", f"{image}:$", str(host),
            "--meta-format", "inf-trad", "--name", "MYNAME",
        )
        assert r.exit_code == 0, r.output
        got = _names(runner, image)
        assert "MYNAME" in got and "test8/3" not in got

    def test_metadata_still_applied_with_derived_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host = _host_file_with_inf(tmp_path, "test8_3", "test8/3")
        _run(runner, "put", f"{image}:$", str(host), "--meta-format", "inf-trad")
        stat = _run(runner, "stat", "--as", "display", f"{image}:$.test8/3").output
        assert "0x000800" in stat and "0x00B82B" in stat


class TestFileDestNamesFile:
    def test_explicit_leaf_wins_over_sidecar(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host = _host_file_with_inf(tmp_path, "test8_3", "test8/3")
        r = _run(
            runner, "put", f"{image}:$.NAMED", str(host), "--meta-format", "inf-trad"
        )
        assert r.exit_code == 0, r.output
        got = _names(runner, image)
        assert "NAMED" in got and "test8/3" not in got

    def test_name_option_overrides_explicit_leaf(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host = _host_file_with_inf(tmp_path, "test8_3", "test8/3")
        r = _run(
            runner, "put", f"{image}:$.NAMED", str(host),
            "--meta-format", "inf-trad", "--name", "BAR",
        )
        assert r.exit_code == 0, r.output
        got = _names(runner, image)
        assert "BAR" in got and "NAMED" not in got


class TestAdfsSubdirectoryDest:
    def test_existing_subdir_dest_derives_leaf(self, runner: CliRunner, tmp_path: Path):
        image = tmp_path / "a.adl"
        _run(runner, "create", str(image), "--title", "T")
        _run(runner, "mkdir", f"{image}:$.LIB")
        host = _host_file_with_inf(tmp_path, "prog_1", "prog/1")
        r = _run(runner, "put", f"{image}:$.LIB", str(host), "--meta-format", "inf-trad")
        assert r.exit_code == 0, r.output
        out = _run(runner, "ls", "--as", "tsv", f"{image}:$.LIB").output
        names = {ln.split("\t")[0] for ln in out.splitlines() if ln and not ln.startswith("#")}
        assert "prog/1" in names


class TestBulkImportUsesSidecarName:
    def test_import_prefers_inf_name_over_host_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host_dir = tmp_path / "tree"
        host_dir.mkdir()
        _host_file_with_inf(host_dir, "test8_3", "test8/3")
        r = _run(runner, "import", str(image), str(host_dir))
        assert r.exit_code == 0, r.output
        names = _names(runner, image)
        assert "test8/3" in names and "test8_3" not in names

    def test_import_falls_back_to_host_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        host_dir = tmp_path / "tree"
        host_dir.mkdir()
        (host_dir / "PLAIN").write_bytes(b"data")
        r = _run(runner, "import", str(image), str(host_dir))
        assert r.exit_code == 0, r.output
        assert "PLAIN" in _names(runner, image)


class TestStdinDirDest:
    def test_stdin_into_dir_requires_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        r = _run(runner, "put", f"{image}:$", input=b"bytes")
        assert r.exit_code != 0
        assert "name" in r.output.lower()

    def test_stdin_into_dir_with_name(self, runner: CliRunner, tmp_path: Path):
        image = _make_dfs(runner, tmp_path)
        r = _run(runner, "put", f"{image}:$", "--name", "PIPED", input=b"bytes")
        assert r.exit_code == 0, r.output
        assert "PIPED" in _names(runner, image)
