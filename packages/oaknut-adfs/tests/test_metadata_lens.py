"""The ADFS mount's default metadata lens.

The lens follows the directory format, not the free-space map: the 8-bit
S/M/L shapes (Old directories) prefer raw load/exec ``addresses``, while
the Arthur/RISC OS shapes prefer a decoded ``type-date``. D-format is the
telling case — it is Arthur-era and filetype-aware, yet pairs New
directories with the *Old* map, so an is-new-map test would misclassify
it. The directory-format predicate lands it on ``type-date`` correctly.
"""

from __future__ import annotations

from oaknut.adfs import ADFS, ADFS_S
from oaknut.filesystem import (
    Lens,
    MetadataLensed,
    create_filesystem,
    reader_for,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_RISCOS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-riscos"
_D_ARTHUR = _RISCOS_DIRPATH / "D_Arthur_Welcome.adf"
_E_RISCOS = _RISCOS_DIRPATH / "E_RISCOS310_NewLook.adf"


def _mount_file(image_filepath):
    filesystem = create_filesystem("adfs")
    reader = reader_for(image_filepath, writable=False).__enter__()
    return reader, filesystem.open(reader, filesystem.probe(reader).geometry)


def _mount_created(tmp_path):
    image_filepath = tmp_path / "test.ads"
    with ADFS.create_file(str(image_filepath), ADFS_S, title="TESTDISC"):
        pass
    return _mount_file(image_filepath)


def test_adfs_mount_declares_a_lens(tmp_path):
    _, mount = _mount_created(tmp_path)
    assert isinstance(mount, MetadataLensed)


def test_old_directory_smsl_prefers_addresses(tmp_path):
    _, mount = _mount_created(tmp_path)
    assert mount.metadata_lens is Lens.ADDRESSES


def test_d_format_arthur_prefers_type_date():
    _, mount = _mount_file(_D_ARTHUR)
    assert mount.metadata_lens is Lens.TYPE_DATE


def test_new_map_e_prefers_type_date():
    _, mount = _mount_file(_E_RISCOS)
    assert mount.metadata_lens is Lens.TYPE_DATE
