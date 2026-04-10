"""Tests for the oaknut_dfs.basic module.

The tokeniser and detokeniser are stubs that raise NotImplementedError
until the real implementation lands. These tests lock in the module's
public API shape so the stubs can be replaced with working code
without disturbing callers.
"""

import pytest

from oaknut_dfs import basic


class TestConstants:

    def test_bbc_basic_load_address(self):
        assert basic.BBC_BASIC_LOAD_ADDRESS == 0x1900

    def test_electron_basic_load_address(self):
        assert basic.ELECTRON_BASIC_LOAD_ADDRESS == 0x0E00


class TestTokeniseStub:

    def test_tokenise_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            basic.tokenise("10 PRINT \"Hello\"")

    def test_tokenise_raises_on_empty_input(self):
        with pytest.raises(NotImplementedError):
            basic.tokenise("")


class TestDetokeniseStub:

    def test_detokenise_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            basic.detokenise(b"\x0d\xff")

    def test_detokenise_raises_on_empty_input(self):
        with pytest.raises(NotImplementedError):
            basic.detokenise(b"")


class TestModuleIsolation:
    """The basic module is destined for a standalone oaknut-basic
    package, so it must not import anything from the rest of
    oaknut_dfs. Guard against regressions."""

    def test_no_oaknut_dfs_imports_in_basic(self):
        import ast
        from pathlib import Path

        source = Path(basic.__file__).read_text()
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or not node.module.startswith(
                    "oaknut_dfs"
                ), f"basic.py must not import from oaknut_dfs: {ast.dump(node)}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("oaknut_dfs"), (
                        f"basic.py must not import from oaknut_dfs: "
                        f"{alias.name}"
                    )
