"""Tests for the fused IMAGE[:PATH] parser."""

from __future__ import annotations

from pathlib import Path

import click
import pytest
from oaknut.disc.cli_paths import parse_file_spec


class TestParseImageArg:
    """Tests for the fused IMAGE[:PATH] parser.

    Every command accepts a single positional spec where the host image
    path and the optional in-image path are joined by a colon. The
    colon splits at the first non-Windows-drive colon; any subsequent
    colon belongs to the in-image side (which lets ``adfs:``/``afs:``/
    ``dfs:`` filing-system prefixes pass through unchanged).
    """

    def _make_image(self, tmp_path: Path, name: str = "disc.ssd") -> Path:
        img = tmp_path / name
        img.write_bytes(b"\x00" * 100)
        return img

    def test_bare_image(self, tmp_path: Path) -> None:
        img = self._make_image(tmp_path)
        image, in_image = parse_file_spec(str(img))
        assert image == img
        assert in_image == ""

    def test_fused_form(self, tmp_path: Path) -> None:
        img = self._make_image(tmp_path)
        image, in_image = parse_file_spec(f"{img}:$.Games")
        assert image == img
        assert in_image == "$.Games"

    def test_fused_form_with_fs_prefix(self, tmp_path: Path) -> None:
        # The adfs:/afs:/dfs: prefix sits on the in-image side of the
        # outer image colon and must pass through unchanged.
        img = self._make_image(tmp_path)
        image, in_image = parse_file_spec(f"{img}:afs:$.Library")
        assert image == img
        assert in_image == "afs:$.Library"

    def test_fused_form_empty_in_image(self, tmp_path: Path) -> None:
        # "image:" is a deliberate "fused, but no path" — equivalent to
        # the bare image form; the in-image string is "".
        img = self._make_image(tmp_path)
        image, in_image = parse_file_spec(f"{img}:")
        assert image == img
        assert in_image == ""

    def test_fused_form_image_not_found(self, tmp_path: Path) -> None:
        # Colon in file_spec definitively signals fused intent. When
        # the LHS portion doesn't exist, the error message must quote
        # only that portion, not the whole string, so the user can
        # see immediately what was looked up.
        nonexistent = tmp_path / "missing.ssd"
        with pytest.raises(click.UsageError, match=r"image not found:.*missing\.ssd"):
            parse_file_spec(f"{nonexistent}:$.Games")

    def test_bare_image_not_found(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "missing.ssd"
        with pytest.raises(click.UsageError, match=r"image not found:.*missing\.ssd"):
            parse_file_spec(str(nonexistent))

    def test_windows_drive_letter_skipped(self, tmp_path: Path) -> None:
        # The first colon in C:\... is the drive letter; the next colon
        # is the image/in-image split. Simulate by making the LHS
        # nonexistent and confirming the error quotes the full drive
        # path, not just "C".
        spec = r"C:\images\disc.ssd:$.Hello"
        with pytest.raises(click.UsageError, match=r"image not found:.*C.\\images"):
            parse_file_spec(spec)

    def test_windows_drive_letter_with_real_file(self, tmp_path: Path) -> None:
        # A real directory at tmp_path/C/disc.ssd. The leading portion
        # of the absolute path won't match the X:\ pattern (since
        # tmp_path is /var/... on macOS), so the first colon found
        # after the directory walk should be the image/in-image split.
        d = tmp_path / "C"
        d.mkdir()
        img = d / "disc.ssd"
        img.write_bytes(b"\x00" * 100)
        image, in_image = parse_file_spec(f"{img}:$.Test")
        assert image == img
        assert in_image == "$.Test"
