"""Tests for the AFS filesystem extension and its discovery by recursion."""

from oaknut.filesystem import (
    AcornMetadata,
    Bootable,
    Compactable,
    Confidence,
    HierarchicalDirectories,
    Mount,
    Titled,
    UserDatabase,
    create_filesystem,
    filesystem_names,
    identify,
    reader_for,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

# A real ADFS hard disc with an AFS tail partition.
_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"


def _afs_region_reader(reader):
    """A reader over l3fs's AFS region, via the ADFS host's reserved region."""
    from oaknut.filesystem import region_reader

    identification = create_filesystem("adfs").probe(reader)
    region = identification.reserved_regions[0]
    return region_reader(reader, identification.geometry, region.start_sector, region.num_sectors)


class TestRegistration:
    def test_afs_registered(self):
        assert "afs" in filesystem_names()


class TestRecursiveDiscovery:
    def test_afs_found_only_inside_the_adfs_host(self):
        # The whole-disc candidates must be ADFS only; AFS appears solely
        # as the recursed tail, never as a top-level filesystem.
        results = identify(_L3FS_DAT)
        assert [r.filesystem for r in results] == ["adfs"]
        (tail,) = results[0].contained
        assert tail.filesystem == "afs"
        assert tail.confidence is Confidence.CERTAIN
        assert tail.partition.selector == "afs"


class TestMount:
    def test_open_region_and_read(self):
        with reader_for(_L3FS_DAT) as reader:
            mount = create_filesystem("afs").open(_afs_region_reader(reader))
            names = {e.name for e in mount.iter_entries("$")}
            # The shipped l3fs disc has these user directories.
            assert "HOLMES" in names

    def test_capabilities(self):
        with reader_for(_L3FS_DAT) as reader:
            mount = create_filesystem("afs").open(_afs_region_reader(reader))
            assert isinstance(mount, Mount)
            assert isinstance(mount, HierarchicalDirectories)
            assert isinstance(mount, AcornMetadata)
            assert isinstance(mount, UserDatabase)
            assert isinstance(mount, Titled)  # AFS has a disc name
            # … but no *OPT-style boot option.
            assert not isinstance(mount, Bootable)
            # AFS compaction is not implemented, so the mount must not claim
            # the capability — otherwise `disc compact` would offer it and
            # then fail. Honest advertisement: it simply is not Compactable.
            assert not isinstance(mount, Compactable)
            assert len(mount.user_names()) >= 1


class TestWritableRegion:
    def test_write_through_hard_disc_window_persists(self, tmp_path):
        # l3fs is a linear hard disc, so its AFS tail is a writable window
        # onto the host: a write reaches the file. Copy the fixture so the
        # mutation is isolated, write through the window, reopen, verify.
        import shutil

        image_filepath = tmp_path / "l3fs.dat"
        shutil.copy(_L3FS_DAT, image_filepath)

        afs = create_filesystem("afs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = afs.open(_afs_region_reader(reader))
            mount.write_bytes("$.NEWFILE", b"persisted")
        with reader_for(image_filepath) as reader:
            mount = afs.open(_afs_region_reader(reader))
            assert mount.read_bytes("$.NEWFILE") == b"persisted"

    def test_set_acorn_meta_round_trips(self, tmp_path):
        import shutil

        from oaknut.file import AcornMeta

        image_filepath = tmp_path / "l3fs.dat"
        shutil.copy(_L3FS_DAT, image_filepath)
        afs = create_filesystem("afs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = afs.open(_afs_region_reader(reader))
            mount.write_bytes("$.METAF", b"data")
            mount.set_acorn_meta(
                "$.METAF", AcornMeta(load_address=0x8000, exec_address=0x9000, access=0)
            )
        with reader_for(image_filepath) as reader:
            mount = afs.open(_afs_region_reader(reader))
            meta = mount.acorn_meta("$.METAF")
            assert meta.load_address == 0x8000
            assert meta.exec_address == 0x9000


class TestNotAfs:
    def test_non_afs_region_returns_none(self):
        # A buffer whose sector 1 is not AFS0 is not AFS.
        afs = create_filesystem("afs")
        with reader_for(b"\x00" * 2048) as reader:
            assert afs.probe(reader) is None
