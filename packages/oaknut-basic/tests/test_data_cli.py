"""Tests for the ``oaknut-basic data`` subcommands."""

from __future__ import annotations

import json

from click.testing import CliRunner
from oaknut.basic.cli import cli
from oaknut.basic.datafile import open as open_datafile


def _write_data_file(filepath, values, **kwargs) -> None:
    with open_datafile(filepath, "w", **kwargs) as f:
        for value in values:
            f.write(value)


class TestDecode:
    def test_decode_emits_inferred_bare_array(self, tmp_path):
        src = tmp_path / "in.dat"
        _write_data_file(src, [42, "HELLO", 3.5, -17])
        result = CliRunner().invoke(cli, ["data", "decode", str(src)])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == [42, "HELLO", 3.5, -17]

    def test_decode_reals_render_with_point(self, tmp_path):
        # A real keeps its float repr so it re-parses as a real, not an int.
        src = tmp_path / "in.dat"
        _write_data_file(src, [5.0])
        assert json.loads(CliRunner().invoke(cli, ["data", "decode", str(src)]).output) == [5.0]

    def test_decode_pound_sign(self, tmp_path):
        src = tmp_path / "in.dat"
        _write_data_file(src, ["£100"])
        result = CliRunner().invoke(cli, ["data", "decode", str(src)])
        assert json.loads(result.output) == ["£100"]


class TestEncode:
    def test_encode_round_trips_decode(self, tmp_path):
        out = tmp_path / "out.dat"
        payload = [42, "HELLO", 3.5, -17]
        result = CliRunner().invoke(
            cli, ["data", "encode", "-", str(out)], input=json.dumps(payload)
        )
        assert result.exit_code == 0, result.output
        expected = tmp_path / "expected.dat"
        _write_data_file(expected, payload)
        assert out.read_bytes() == expected.read_bytes()

    def test_encode_bytes_object(self, tmp_path):
        out = tmp_path / "out.dat"
        result = CliRunner().invoke(
            cli, ["data", "encode", "-", str(out)], input=json.dumps([{"bytes": "01ff3a"}])
        )
        assert result.exit_code == 0, result.output
        assert out.read_bytes() == b"\x01\xff\x3a"

    def test_encode_pound_sign_uses_acorn(self, tmp_path):
        out = tmp_path / "out.dat"
        result = CliRunner().invoke(
            cli, ["data", "encode", "-", str(out)], input=json.dumps(["£"])
        )
        assert result.exit_code == 0, result.output
        # 00 (string tag) 01 (length) 60 (pound) — single char, reversal a no-op.
        assert out.read_bytes() == bytes.fromhex("000160")

    def test_encode_rejects_invalid_json(self, tmp_path):
        out = tmp_path / "out.dat"
        result = CliRunner().invoke(cli, ["data", "encode", "-", str(out)], input="not json")
        assert result.exit_code != 0
        assert "JSON" in result.output

    def test_encode_rejects_non_array(self, tmp_path):
        out = tmp_path / "out.dat"
        result = CliRunner().invoke(cli, ["data", "encode", "-", str(out)], input='{"a": 1}')
        assert result.exit_code != 0

    def test_encode_rejects_bool(self, tmp_path):
        out = tmp_path / "out.dat"
        result = CliRunner().invoke(cli, ["data", "encode", "-", str(out)], input="[true]")
        assert result.exit_code != 0

    def test_encode_rejects_null(self, tmp_path):
        out = tmp_path / "out.dat"
        result = CliRunner().invoke(cli, ["data", "encode", "-", str(out)], input="[null]")
        assert result.exit_code != 0


class TestRoundTrip:
    def test_decode_then_encode_reproduces_bytes(self, tmp_path):
        src = tmp_path / "in.dat"
        _write_data_file(src, [1, "two", 3.5, -4, "£", 0.0])
        decoded = CliRunner().invoke(cli, ["data", "decode", str(src)]).output
        out = tmp_path / "out.dat"
        CliRunner().invoke(cli, ["data", "encode", "-", str(out)], input=decoded)
        assert out.read_bytes() == src.read_bytes()


class TestInspect:
    def test_inspect_json_is_faithful(self, tmp_path):
        src = tmp_path / "in.dat"
        _write_data_file(src, [42, "HELLO", 3.5])
        result = CliRunner().invoke(cli, ["data", "inspect", str(src), "--as", "json"])
        assert result.exit_code == 0, result.output
        rows = json.loads(result.output)["reports"]["records"]["rows"]
        assert [r["type"] for r in rows] == ["int", "string", "real"]
        assert rows[0]["value"] == 42 and isinstance(rows[0]["value"], int)
        assert rows[2]["value"] == 3.5

    def test_inspect_tsv(self, tmp_path):
        src = tmp_path / "in.dat"
        _write_data_file(src, [42, "HELLO"])
        result = CliRunner().invoke(cli, ["data", "inspect", str(src), "--as", "tsv"])
        assert result.exit_code == 0, result.output
        assert "42" in result.output
        assert "HELLO" in result.output
