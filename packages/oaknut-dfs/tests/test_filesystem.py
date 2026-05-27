"""Tests for the DFS-family filesystem extensions on the oaknut.filesystem axis."""

from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.filesystem import (
    AcornMetadata,
    Bootable,
    Confidence,
    HierarchicalDirectories,
    Mount,
    Titled,
    create_filesystem,
    filesystem_names,
    identify,
    reader_for,
)


def _make_dfs_image(tmp_path):
    image_filepath = tmp_path / "test.ssd"
    with DFS.create_file(image_filepath, ACORN_DFS_80T_SINGLE_SIDED, title="DEMO") as dfs:
        (dfs.root / "$.HELLO").write_bytes(
            b"hello world", load_address=0x1900, exec_address=0x8023
        )
        (dfs.root / "$.DATA").write_bytes(b"\x00\x01\x02\x03", load_address=0xFF00)
    return image_filepath


def _watford_image_bytes() -> bytes:
    buffer = bytearray(204800)
    buffer[0:10] = b"WATFORD   "
    buffer[256 + 6] = 0x03
    buffer[256 + 7] = 0x20
    buffer[512:524] = b"\xaa" * 12
    buffer[768 + 6] = 0x03
    buffer[768 + 7] = 0x20
    return bytes(buffer)


class TestRegistration:
    def test_both_dfs_filesystems_registered(self):
        names = filesystem_names()
        assert "acorn-dfs" in names
        assert "watford-dfs" in names


class TestProbe:
    def test_identifies_acorn_dfs(self, tmp_path):
        results = identify(_make_dfs_image(tmp_path))
        assert results[0].filesystem == "acorn-dfs"
        assert results[0].confidence is Confidence.PROBABLE
        # 80T SS proposed, with the byte-identical 40T DS as an ambiguity.
        assert results[0].geometry is not None
        assert len(results[0].ambiguities) == 1

    def test_identifies_watford_dfs(self):
        results = identify(_watford_image_bytes(), suffix_hint=".ssd")
        assert results[0].filesystem == "watford-dfs"
        assert results[0].confidence is Confidence.STRONG

    def test_acorn_excludes_watford(self):
        # The two are mutually exclusive: only watford-dfs identifies a
        # Watford image.
        families = {r.filesystem for r in identify(_watford_image_bytes())}
        assert families == {"watford-dfs"}


class TestMount:
    def test_open_lists_and_reads(self, tmp_path):
        image_filepath = _make_dfs_image(tmp_path)
        filesystem = create_filesystem("acorn-dfs")
        with reader_for(image_filepath) as reader:
            identification = filesystem.probe(reader)
            mount = filesystem.open(reader, identification.geometry)

            assert isinstance(mount, Mount)
            # DFS's root is the nameless virtual catalogue holding the
            # directory letters, not $ itself (a sibling of A, B, …).
            assert mount.path_root() == ""
            assert {entry.name for entry in mount.iter_entries("")} == {"$"}
            names = {entry.name for entry in mount.iter_entries("$")}
            assert {"HELLO", "DATA"} <= names
            assert mount.read_bytes("$.HELLO") == b"hello world"
            assert mount.exists("$.HELLO")

    def test_capabilities(self, tmp_path):
        image_filepath = _make_dfs_image(tmp_path)
        filesystem = create_filesystem("acorn-dfs")
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            # DFS carries Acorn metadata and a disc title/boot option …
            assert isinstance(mount, AcornMetadata)
            assert isinstance(mount, Titled)
            assert isinstance(mount, Bootable)
            # … but is flat, so it is not hierarchical.
            assert not isinstance(mount, HierarchicalDirectories)

            meta = mount.acorn_meta("$.HELLO")
            assert meta.load_address == 0x1900
            assert meta.exec_address == 0x8023
            assert mount.title == "DEMO"


class TestGeometryGrammar:
    def test_presets(self):
        grammar = create_filesystem("acorn-dfs").geometry_grammar()
        assert "80t-ss" in grammar.preset_names()
        geom = grammar.parse("80t-ss")
        assert geom.image_size == 204800
