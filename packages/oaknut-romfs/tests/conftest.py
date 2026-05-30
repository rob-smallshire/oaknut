"""Pytest bootstrap for oaknut-romfs.

Under pytest's importlib mode (required for PEP 420 namespace packages)
the workspace root is not auto-injected into sys.path, so
``from tests.fixtures import ...`` won't resolve without help. This
restores both the package's own ``tests/`` directory and the workspace
root, matching every sibling package's conftest.
"""

import sys
from pathlib import Path

_TESTS_DIRPATH = Path(__file__).parent
_WORKSPACE_ROOT = _TESTS_DIRPATH.parent.parent.parent
for _path in (_TESTS_DIRPATH, _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
