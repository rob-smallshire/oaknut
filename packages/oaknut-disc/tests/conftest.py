"""Pytest bootstrap for oaknut-disc.

Under pytest's importlib mode (required for PEP 420 namespace
packages) neither the package's own ``tests`` directory nor the
workspace root is auto-injected into ``sys.path``. Inserting both
here restores the shared import patterns.
"""

import sys
from pathlib import Path

_TESTS_DIRPATH = Path(__file__).parent
_WORKSPACE_ROOT = _TESTS_DIRPATH.parent.parent.parent
for _path in (_TESTS_DIRPATH, _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import pytest  # noqa: E402
from click.testing import CliRunner  # noqa: E402
from oaknut.adfs import ADFS, ADFS_L  # noqa: E402
from oaknut.afs.wfsinit import AFSSizeSpec, InitSpec, UserSpec, initialise  # noqa: E402
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS  # noqa: E402
from oaknut.disc.cli import cli  # noqa: E402


@pytest.fixture
def runner() -> CliRunner:
    """Click test runner."""
    return CliRunner()


@pytest.fixture
def dfs_image_filepath(tmp_path: Path) -> Path:
    """Create a DFS .ssd image with a couple of test files."""
    filepath = tmp_path / "test.ssd"
    with DFS.create_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, title="TestDFS") as dfs:
        (dfs.root / "$.Hello").write_bytes(b"Hello world", load_address=0x1900, exec_address=0x8023)
        (dfs.root / "$.Data").write_bytes(b"\x00\x01\x02\x03", load_address=0xFF00)
    return filepath


@pytest.fixture
def adfs_image_filepath(tmp_path: Path) -> Path:
    """Create an ADFS-L floppy image with test files and a directory."""
    filepath = tmp_path / "test.adl"
    with ADFS.create_file(filepath, ADFS_L, title="TestADFS") as adfs:
        (adfs.root / "Hello").write_bytes(
            b"Hello ADFS",
            load_address=0x1900,
            exec_address=0x8023,
        )
        (adfs.root / "Games").mkdir()
        (adfs.root / "Games" / "Elite").write_bytes(
            b"Elite data",
            load_address=0x1100,
            exec_address=0x1100,
        )
    return filepath


@pytest.fixture
def afs_image_filepath(tmp_path: Path) -> Path:
    """Create an ADFS-L image with an initialised AFS partition."""
    filepath = tmp_path / "scsi0.adl"
    with ADFS.create_file(filepath, ADFS_L) as _adfs:
        pass
    with ADFS.from_file(filepath, mode="r+b") as adfs:
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="TestAFS",
                size=AFSSizeSpec.cylinders(20),
                users=[],
            ),
        )
    # Put a test file into the AFS partition.
    with ADFS.from_file(filepath, mode="r+b") as adfs:
        afs = adfs.afs_partition
        (afs.root / "Greeting").write_bytes(
            b"Hello AFS",
            load_address=0,
            exec_address=0,
        )
        afs.flush()
    return filepath


@pytest.fixture
def afs_image_with_spare_slot(tmp_path: Path) -> Path:
    """Create an AFS image initialised with Syst and alice.

    Tests can remove alice (tombstone) or use the existing allocation
    for user mutation tests.
    """
    filepath = tmp_path / "spare.adl"
    with ADFS.create_file(filepath, ADFS_L) as _adfs:
        pass
    with ADFS.from_file(filepath, mode="r+b") as adfs:
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="SpareSlot",
                size=AFSSizeSpec.cylinders(20),
                users=[
                    UserSpec("alice"),
                ],
            ),
        )
    return filepath


@pytest.fixture
def adfs_no_afs_filepath(tmp_path: Path) -> Path:
    """Create an ADFS-L image without any AFS partition."""
    filepath = tmp_path / "nofs.adl"
    with ADFS.create_file(filepath, ADFS_L, title="NoAFS") as _adfs:
        pass
    return filepath


@pytest.fixture
def dfs_image_many_files(tmp_path: Path) -> Path:
    """DFS image with several files in $ and in directory G.

    Used by cp glob / recursive tests that need multiple source files.
    """
    filepath = tmp_path / "many.ssd"
    with DFS.create_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, title="ManyDFS") as dfs:
        (dfs.root / "$.Hello").write_bytes(b"hello-data", load_address=0x1900)
        (dfs.root / "$.Help").write_bytes(b"help-data", load_address=0x2000)
        (dfs.root / "$.Data").write_bytes(b"data-data", load_address=0x3000)
        (dfs.root / "G.FOO").write_bytes(b"g-foo", load_address=0x4000)
        (dfs.root / "G.BAR").write_bytes(b"g-bar", load_address=0x5000)
    return filepath


@pytest.fixture
def adfs_image_tree(tmp_path: Path) -> Path:
    """ADFS-L image with a nested directory tree.

    Layout::

        $/
          Root1          (file)
          Dir/
            Inside       (file)
            Sub/
              Deep       (file)
    """
    filepath = tmp_path / "tree.adl"
    with ADFS.create_file(filepath, ADFS_L, title="TreeADFS") as adfs:
        (adfs.root / "Root1").write_bytes(b"root1-data", load_address=0x1000)
        (adfs.root / "Dir").mkdir()
        (adfs.root / "Dir" / "Inside").write_bytes(b"inside-data", load_address=0x2000)
        (adfs.root / "Dir" / "Sub").mkdir()
        (adfs.root / "Dir" / "Sub" / "Deep").write_bytes(b"deep-data", load_address=0x3000)
    return filepath


@pytest.fixture
def adfs_empty_filepath(tmp_path: Path) -> Path:
    """Empty ADFS-L image suitable as a copy destination."""
    filepath = tmp_path / "empty.adl"
    with ADFS.create_file(filepath, ADFS_L, title="Empty"):
        pass
    return filepath


@pytest.fixture
def dfs_empty_filepath(tmp_path: Path) -> Path:
    """Empty DFS image suitable as a copy destination."""
    filepath = tmp_path / "empty.ssd"
    with DFS.create_file(filepath, ACORN_DFS_80T_SINGLE_SIDED, title="Empty"):
        pass
    return filepath


@pytest.fixture
def adfs_hard_no_afs_filepath(tmp_path: Path) -> Path:
    """ADFS hard-disc image (10 MB) without an AFS partition."""
    filepath = tmp_path / "hard_no_afs.dat"
    with ADFS.create_file(filepath, capacity_bytes=10_000_000, title="Bigone"):
        pass
    return filepath


@pytest.fixture
def adfs_hard_with_afs_filepath(tmp_path: Path) -> Path:
    """ADFS hard-disc image (10 MB) with an initialised AFS partition."""
    filepath = tmp_path / "hard_with_afs.dat"
    with ADFS.create_file(filepath, capacity_bytes=10_000_000, title="Split"):
        pass
    with ADFS.from_file(filepath, mode="r+b") as adfs:
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="TwinFS",
                size=AFSSizeSpec.cylinders(100),
                users=[UserSpec("holmes")],
            ),
        )
    return filepath


@pytest.fixture
def afs_image_with_access_bytes(tmp_path: Path) -> Path:
    """AFS image with files whose access bytes span the common cases.

    Each file's ``disc ls`` symbolic column should round-trip back to
    the value it was written with.  Exercises issue #12.
    """
    from oaknut.afs.access import AFSAccess

    filepath = tmp_path / "access_bytes.adl"
    with ADFS.create_file(filepath, ADFS_L) as _adfs:
        pass
    with ADFS.from_file(filepath, mode="r+b") as adfs:
        initialise(
            adfs,
            spec=InitSpec(
                disc_name="AccessTest",
                size=AFSSizeSpec.cylinders(20),
                users=[],
            ),
        )
    with ADFS.from_file(filepath, mode="r+b") as adfs:
        afs = adfs.afs_partition
        (afs.root / "alpha").write_bytes(
            b"a", access=AFSAccess.from_string("WR/R")
        )
        (afs.root / "bravo").write_bytes(
            b"b", access=AFSAccess.from_string("LWR/R")
        )
        (afs.root / "charlie").write_bytes(
            b"c", access=AFSAccess.from_string("WR/WR")
        )
        (afs.root / "delta").write_bytes(
            b"d", access=AFSAccess.from_string("/")
        )
        (afs.root / "Folder").mkdir()
        afs.flush()
    return filepath
