"""Test configuration for oaknut-codecs.

Pytest runs in ``--import-mode=importlib`` for the PEP 420 namespace
package, which means test directories are not auto-injected onto
``sys.path``. Restore the package's own ``tests/`` directory and the
workspace root so ``helpers`` and ``tests.fixtures`` imports resolve.
"""

import sys
from pathlib import Path

_TESTS_DIRPATH = Path(__file__).parent
_WORKSPACE_ROOT = _TESTS_DIRPATH.parent.parent.parent
for _path in (_TESTS_DIRPATH, _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))
