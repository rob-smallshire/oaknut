"""Tests for the ADFS filesystem extension on the oaknut.filesystem axis."""

import pytest
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

    _RISCOS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-riscos"

    @pytest.mark.parametrize(
        "image,evidence_fragment",
        [
            # Old map + New directory (root at sector 4, 'Hugo' signature).
            ("D_Arthur_Welcome.adf", "New-directory root"),
            ("D_RISCOS310_App1.adf", "New-directory root"),
            # New map, single-zone (E) — no old-map signature at all.
            ("E_RISCOS310_NewLook.adf", "New map FileCore disc record"),
        ],
    )
    def test_identifies_risc_os_specimens_strong(self, image, evidence_fragment):
        # Regression: the probe once recognised only the old-map old-directory
        # signature, so every New-directory and New-map disc — the whole RISC OS
        # family — failed identification and could not be opened by the CLI.
        results = identify(self._RISCOS_DIRPATH / image)
        adfs = next((r for r in results if r.filesystem == "adfs"), None)
        assert adfs is not None, f"{image} not identified as ADFS"
        assert adfs.confidence is Confidence.STRONG
        assert any(evidence_fragment in e for e in adfs.evidence), adfs.evidence

    @pytest.mark.parametrize(
        "variant,zones_fragment",
        [("f", "4-zone"), ("g", "8-zone"), ("e+", "Big directories"), ("f+", "Big directories")],
    )
    def test_identifies_created_new_map_variants_strong(self, variant, zones_fragment, tmp_path):
        filesystem = create_filesystem("adfs")
        geometry = filesystem.geometry_grammar().parse(variant)
        image = tmp_path / f"disc_{variant.replace('+', 'p')}.adf"
        filesystem.create(image, geometry, title="X")
        results = identify(image)
        adfs = next(r for r in results if r.filesystem == "adfs")
        assert adfs.confidence is Confidence.STRONG
        assert any(zones_fragment in e for e in adfs.evidence), adfs.evidence


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
        assert set(grammar.preset_names()) == {
            "s", "m", "l", "d", "e", "e+", "f", "f+", "g", "g+",
        }
        assert grammar.parse("l").image_size == 655360
        # ADFS also accepts open-ended hard-disc geometry.
        hd = grammar.parse("cylinders=200,heads=4,spt=33")
        assert hd.num_sectors == 200 * 4 * 33

    def test_new_map_presets_carry_a_variant_and_size(self):
        grammar = create_filesystem("adfs").geometry_grammar()
        # D, E and E+ share a size; the variant tag is what tells them apart.
        for name in ("d", "e", "e+"):
            geo = grammar.parse(name)
            assert geo.image_size == 819200
            assert geo.variant == name
        assert grammar.parse("f").image_size == 1638400
        assert grammar.parse("g").image_size == 3276800


class TestReadOnlyOpen:
    """``read_only=True`` guarantees a committed image cannot be modified."""

    def test_read_only_open_cannot_mutate_the_file(self, tmp_path):
        filepath = tmp_path / "disc.ads"
        with ADFS.create_file(str(filepath), ADFS_S, title="RO") as adfs:
            (adfs.root / "$.KEEP").write_bytes(b"original")
        before = filepath.read_bytes()

        with ADFS.from_file(filepath, read_only=True) as adfs:
            assert (adfs.root / "$.KEEP").read_bytes() == b"original"
            with pytest.raises((TypeError, ValueError, BufferError)):
                (adfs.root / "$.NEW").write_bytes(b"x")
        assert filepath.read_bytes() == before


class TestCreateVariants:
    """Each ADFS floppy format is reachable through its ``--geometry`` preset."""

    @pytest.mark.parametrize(
        "preset,new_map,big_dir",
        [
            ("d", False, False),
            ("e", True, False),
            ("e+", True, True),
            ("f", True, False),
            ("f+", True, True),
            ("g", True, False),
            ("g+", True, True),
        ],
    )
    def test_preset_creates_the_right_format(self, tmp_path, preset, new_map, big_dir):
        from oaknut.adfs.directory import BigDirectoryFormat

        filesystem = create_filesystem("adfs")
        geometry = filesystem.geometry_grammar().parse(preset)
        image_filepath = tmp_path / f"disc_{preset.replace('+', 'p')}.adf"
        filesystem.create(image_filepath, geometry, title="VARIANT")

        with ADFS.from_file(image_filepath) as adfs:
            assert adfs.is_new_map is new_map
            assert isinstance(adfs._dir_format, BigDirectoryFormat) is big_dir
            # New-directory discs keep the title in the root directory; Big
            # directories have no title field, so their label comes from the
            # disc record's disc name — either way it round-trips.
            assert adfs.title == "VARIANT"
            (adfs.root / "$.HELLO").write_bytes(b"hi" * 100)
            assert (adfs.root / "$.HELLO").read_bytes() == b"hi" * 100
            assert adfs.validate() == []
