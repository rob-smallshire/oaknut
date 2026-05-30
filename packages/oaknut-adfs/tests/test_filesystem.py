"""Tests for the ADFS filesystem extension on the oaknut.filesystem axis."""

from oaknut.adfs import ADFS, ADFS_S
from oaknut.filesystem import (
    AcornMetadata,
    Bootable,
    Confidence,
    HierarchicalDirectories,
    Mount,
    RegionHost,
    Titled,
    create_filesystem,
    filesystem_names,
    identify,
    reader_for,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_L3FS_DAT = REFERENCE_IMAGES_DIRPATH / "l3fs" / "l3fs-wfsinit.dat"


def _make_adfs_image(tmp_path):
    image_filepath = tmp_path / "test.ads"
    with ADFS.create_file(str(image_filepath), ADFS_S, title="TESTDISC") as adfs:
        (adfs.root / "$.HELLO").write_bytes(
            b"hello world", load_address=0x1900, exec_address=0x8023
        )
        (adfs.root / "$.GAMES").mkdir()
    return image_filepath


class TestRegistration:
    def test_adfs_registered(self):
        assert "adfs" in filesystem_names()


class TestProbe:
    def test_identifies_created_floppy_strong(self, tmp_path):
        results = identify(_make_adfs_image(tmp_path))
        assert results[0].filesystem == "adfs"
        assert results[0].confidence is Confidence.STRONG
        # A plain floppy reserves no tail.
        assert results[0].contained == ()

    def test_reserved_tail_is_recursed(self):
        # The l3fs hard disc reserves a tail; ADFS reports it and the
        # coordinator recurses in. With oaknut-afs installed it resolves
        # to AFS (this asserts ADFS's region-finding, not AFS itself).
        results = identify(_L3FS_DAT)
        adfs = next(r for r in results if r.filesystem == "adfs")
        assert len(adfs.contained) == 1
        region = adfs.contained[0]
        assert region.partition.start_sector == 264  # logical sector of the tail
        assert region.filesystem == "afs"


class TestMount:
    def test_open_lists_reads_and_mkdir(self, tmp_path):
        filesystem = create_filesystem("adfs")
        with reader_for(_make_adfs_image(tmp_path)) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            names = {e.name for e in mount.iter_entries("$")}
            assert {"HELLO", "GAMES"} <= names
            assert mount.read_bytes("$.HELLO") == b"hello world"
            mount.make_directory("$.NEWDIR")
            assert mount.exists("$.NEWDIR")

    def test_writable_open_persists_to_file(self, tmp_path):
        # A writable reader makes mount mutations reach the file: write a
        # file and make a directory, then reopen from disk and find them.
        filesystem = create_filesystem("adfs")
        image_filepath = _make_adfs_image(tmp_path)
        with reader_for(image_filepath, writable=True) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            mount.make_directory("$.NEWDIR")
            mount.write_bytes("$.GREET", b"hi there")
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            assert mount.exists("$.NEWDIR")
            assert mount.read_bytes("$.GREET") == b"hi there"

    def test_set_acorn_meta_round_trips(self, tmp_path):
        from oaknut.file import AcornMeta

        filesystem = create_filesystem("adfs")
        image_filepath = _make_adfs_image(tmp_path)
        with reader_for(image_filepath, writable=True) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            mount.set_acorn_meta(
                "$.HELLO", AcornMeta(load_address=0xABCD, exec_address=0x1234, access=0x0F)
            )
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            meta = mount.acorn_meta("$.HELLO")
            assert meta.load_address == 0xABCD
            assert meta.exec_address == 0x1234

    def test_capabilities(self, tmp_path):
        filesystem = create_filesystem("adfs")
        with reader_for(_make_adfs_image(tmp_path)) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            assert isinstance(mount, Mount)
            assert isinstance(mount, HierarchicalDirectories)
            assert isinstance(mount, AcornMetadata)
            assert isinstance(mount, Titled)
            assert isinstance(mount, Bootable)
            assert isinstance(mount, RegionHost)
            from oaknut.filesystem import WildcardMatching

            assert isinstance(mount, WildcardMatching)
            assert mount.wildcard_syntax.chars == "*#"  # Acorn wildcards
            assert mount.title == "TESTDISC"
            assert mount.reserved_regions() == ()  # a floppy reserves nothing


class TestGeometryGrammar:
    def test_floppy_presets_and_winchester_param(self):
        grammar = create_filesystem("adfs").geometry_grammar()
        assert set(grammar.preset_names()) == {"s", "m", "l"}
        assert grammar.parse("l").image_size == 655360
        # ADFS also accepts open-ended hard-disc geometry.
        hd = grammar.parse("cylinders=200,heads=4,spt=33")
        assert hd.num_sectors == 200 * 4 * 33
