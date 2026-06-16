"""Tests for the DFS-family filesystem extensions on the oaknut.filesystem axis."""

import pytest
from oaknut.dfs import ACORN_DFS_80T_SINGLE_SIDED, DFS
from oaknut.filesystem import (
    AcornMetadata,
    Bootable,
    Confidence,
    HierarchicalDirectories,
    Mount,
    Titled,
    Volume,
    create_filesystem,
    filesystem_names,
    identify,
    reader_for,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH


def _make_dfs_image(tmp_path):
    image_filepath = tmp_path / "test.ssd"
    with DFS.create_file(image_filepath, ACORN_DFS_80T_SINGLE_SIDED, title="DEMO") as dfs:
        (dfs.root / "$.HELLO").write_bytes(b"hello world", load_address=0x1900, exec_address=0x8023)
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

    def test_identifies_truncated_image(self, tmp_path):
        # A truncated DFS image (file omits trailing unused sectors, so the
        # catalogue declares more than the file holds) is still recognised —
        # the filing system reads it transparently (issue #1).
        image_filepath = _make_dfs_image(tmp_path)
        full = image_filepath.read_bytes()
        truncated = tmp_path / "truncated.ssd"
        truncated.write_bytes(full[: 136 * 256])  # keep only the first 136 sectors
        results = identify(truncated)
        assert results and results[0].filesystem == "acorn-dfs"

    def test_identifies_watford_dfs(self):
        results = identify(_watford_image_bytes(), suffix_hint=".ssd")
        assert results[0].filesystem == "watford-dfs"
        assert results[0].confidence is Confidence.STRONG

    def test_acorn_excludes_watford(self):
        # The two are mutually exclusive: only watford-dfs identifies a
        # Watford image.
        families = {r.filesystem for r in identify(_watford_image_bytes())}
        assert families == {"watford-dfs"}

    def test_identifies_owlet_disc_with_bogus_declared_total(self):
        # Owlet (bbcmicrobot.com) writes a well-formed DFS catalogue but
        # stamps a bogus total-sector count: boot/sectors byte 0x30 and
        # low byte 0x03 decode to 3 sectors, which is neither >= 4 nor a
        # multiple of 10. The self-declared total is unreliable; the
        # catalogue itself (title "BBCMICROBOT", 4 files incl. !BOOT, all
        # entries fitting the real 800-sector surface) is valid DFS, so
        # identify must still recognise it.
        image_filepath = REFERENCE_IMAGES_DIRPATH / "owlet" / "owlet-dla.ssd"
        results = identify(image_filepath)
        acorn = [r for r in results if r.filesystem == "acorn-dfs"]
        assert acorn, f"acorn-dfs not identified; got {[r.filesystem for r in results]}"

    def test_identifies_disc_with_control_characters_in_title(self):
        # The Oxford Pascal 80-track disc carries decorative control
        # characters in its 12-byte title (a form-feed, CR and LF around
        # "Pascal"). These are 7-bit-clean, so the catalogue is valid DFS
        # — 22 files, 800 sectors matching the surface — but the title
        # heuristic used to reject any byte <= 31. A control-character
        # title must not disqualify a well-formed catalogue.
        image_filepath = (
            REFERENCE_IMAGES_DIRPATH / "oxford-pascal" / "OXFORD PASCAL (80 TRACK).SSD"
        )
        results = identify(image_filepath)
        acorn = [r for r in results if r.filesystem == "acorn-dfs"]
        assert acorn, f"acorn-dfs not identified; got {[r.filesystem for r in results]}"

    def test_opens_oxford_pascal_40_track(self):
        # The 40-track Oxford Pascal disc is 102528 bytes — 400 whole
        # sectors plus a 128-byte trailer, so its length is not a clean
        # multiple of the sector size. Identification matched on the
        # floored sector count, but geometry proposal returned None for
        # the odd length, so opening (what `disc ls` does) crashed. A
        # disc that identifies must also propose a geometry and open.
        image_filepath = (
            REFERENCE_IMAGES_DIRPATH / "oxford-pascal" / "OXFORD PASCAL V2.1c (40 TRACK).SSD"
        )
        results = identify(image_filepath)
        acorn = [r for r in results if r.filesystem == "acorn-dfs"]
        assert acorn, f"acorn-dfs not identified; got {[r.filesystem for r in results]}"
        assert acorn[0].geometry is not None, "no geometry proposed for an odd-length image"

        filesystem = create_filesystem("acorn-dfs")
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            names = {entry.name for entry in mount.iter_entries(mount.path_root())}
        assert names, "expected catalogue entries"

    def test_top_bit_set_title_still_disqualifies(self, tmp_path):
        # The 7-bit-cleanliness of the title remains a hard signal: a
        # high-bit byte in the title field is not DFS, so even an
        # otherwise well-formed catalogue must be rejected. (A control
        # character is tolerated; a top-bit-set byte is not.)
        good_filepath = _make_dfs_image(tmp_path)
        assert any(r.filesystem == "acorn-dfs" for r in identify(good_filepath))
        raw = bytearray(good_filepath.read_bytes())
        raw[1] = 0xC1  # top-bit-set byte in the title field
        # Write the doctored copy to a fresh path: create_file/identify
        # leave the source memory-mapped, and Windows forbids reopening a
        # mapped file for writing, so we must not overwrite it in place.
        bad_filepath = tmp_path / "topbit.ssd"
        bad_filepath.write_bytes(raw)
        assert not any(r.filesystem == "acorn-dfs" for r in identify(bad_filepath))


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

    def test_writable_open_persists_to_file(self, tmp_path):
        image_filepath = _make_dfs_image(tmp_path)
        filesystem = create_filesystem("acorn-dfs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            mount.write_bytes("$.GREET", b"hi there")
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            assert mount.read_bytes("$.GREET") == b"hi there"

    def test_set_acorn_meta_round_trips(self, tmp_path):
        from oaknut.file import Access, AcornMeta

        image_filepath = _make_dfs_image(tmp_path)
        filesystem = create_filesystem("acorn-dfs")
        with reader_for(image_filepath, writable=True) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            mount.set_acorn_meta(
                "$.HELLO", AcornMeta(load_address=0x2000, exec_address=0x3000, access=int(Access.L))
            )
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            meta = mount.acorn_meta("$.HELLO")
            assert meta.load_address == 0x2000
            assert meta.exec_address == 0x3000
            assert meta.access & Access.L

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

            # It globs with Acorn wildcards: * and #, with ? an ordinary
            # filename character.
            from oaknut.filesystem import WildcardMatching

            assert isinstance(mount, WildcardMatching)
            assert mount.wildcard_syntax.chars == "*#"
            assert mount.is_pattern("HE#")
            assert not mount.is_pattern("ZALAGA?")  # ? is literal here
            assert mount.matches("ZALAGA?", "ZALAGA?")
            assert not mount.matches("ZALAGA?", "ZALAGAB")

            meta = mount.acorn_meta("$.HELLO")
            assert meta.load_address == 0x1900
            assert meta.exec_address == 0x8023
            assert mount.title == "DEMO"

    def test_storage_order_tracks_sectors_not_names(self, tmp_path):
        from oaknut.filesystem import StorageOrdered

        # ZED is written first so it occupies the lowest sectors; ABLE
        # follows in higher sectors. Storage order must therefore put ZED
        # before ABLE — the on-disc order, not the alphabetical one.
        image_filepath = tmp_path / "ord.ssd"
        with DFS.create_file(image_filepath, ACORN_DFS_80T_SINGLE_SIDED, title="ORD") as dfs:
            (dfs.root / "$.ZED").write_bytes(b"z" * 300)
            (dfs.root / "$.ABLE").write_bytes(b"a" * 300)
        filesystem = create_filesystem("acorn-dfs")
        with reader_for(image_filepath) as reader:
            mount = filesystem.open(reader, filesystem.probe(reader).geometry)
            assert isinstance(mount, StorageOrdered)
            ordered = sorted(["$.ABLE", "$.ZED"], key=mount.storage_key)
            assert ordered == ["$.ZED", "$.ABLE"]


class TestGeometryGrammar:
    def test_presets(self):
        grammar = create_filesystem("acorn-dfs").geometry_grammar()
        assert "80t-ss" in grammar.preset_names()
        geom = grammar.parse("80t-ss")
        assert geom.image_size == 204800


class TestVolumesAndSplitVolume:
    """The filesystem-owned volume vocabulary: enumeration and parse.

    A double-sided DFS exposes two volumes designated ``:0`` / ``:2``;
    single-sided is one undesignated volume. ``split_volume`` parses the
    Acorn ``:drive.`` prefix back to a surface, forgivingly (any non-zero
    drive is the second side) and stateless (no drive ⇒ side 0).
    """

    def _fs_and_geometry(self, preset):
        fs = create_filesystem("acorn-dfs")
        return fs, fs.geometry_grammar().parse(preset)

    def test_volumes_double_sided(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        assert fs.volumes(geom) == (Volume(":0", 0), Volume(":2", 1))

    def test_volumes_single_sided_is_one_undesignated(self):
        fs, geom = self._fs_and_geometry("80t-ss")
        assert fs.volumes(geom) == (Volume("", 0),)

    def test_designation_round_trips(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        for volume in fs.volumes(geom):
            surface, _geom, _residual = fs.split_volume(f"{volume.designation}.$.X", geom)
            assert surface == volume.surface

    def test_split_no_drive_is_side_zero_whole_path(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        assert fs.split_volume("$.PLANETO", geom) == (0, geom, "$.PLANETO")

    def test_split_explicit_drive_zero(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        assert fs.split_volume(":0.$.PLANETO", geom) == (0, geom, "$.PLANETO")

    def test_split_drive_two(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        assert fs.split_volume(":2.Z.MYDATA", geom) == (1, geom, "Z.MYDATA")

    def test_split_drive_forgiving_any_nonzero(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        for token in (":1", ":2", ":3"):
            surface, _g, residual = fs.split_volume(f"{token}.$.X", geom)
            assert (surface, residual) == (1, "$.X")

    def test_split_digit_directory_shorthand_is_not_a_drive(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        # No leading colon → directory named '2', not drive 2.
        assert fs.split_volume("2.FILE", geom) == (0, geom, "2.FILE")

    def test_split_bare_designation_has_empty_residual(self):
        fs, geom = self._fs_and_geometry("80t-ds")
        assert fs.split_volume(":2", geom) == (1, geom, "")

    def test_split_nonzero_drive_on_single_sided_errors(self):
        from oaknut.filesystem.exceptions import NoSuchVolumeError

        fs, geom = self._fs_and_geometry("80t-ss")
        with pytest.raises(NoSuchVolumeError, match=r":2"):
            fs.split_volume(":2.$.X", geom)

    def test_split_nonzero_drive_implies_double_sided_from_ambiguity(self):
        fs = create_filesystem("acorn-dfs")
        single = fs.geometry_grammar().parse("80t-ss")
        double = fs.geometry_grammar().parse("40t-ds")
        surface, resolved, residual = fs.split_volume(":2.$.X", single, (double,))
        assert surface == 1
        assert resolved is double
        assert residual == "$.X"


class TestOpenSurface:
    """``open(surface=)`` opens an independent side, writably, in place."""

    def test_open_second_side_independent_writes(self, tmp_path):
        from oaknut.dfs import ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED

        image_filepath = tmp_path / "two.dsd"
        with DFS.create_file(image_filepath, ACORN_DFS_80T_DOUBLE_SIDED_INTERLEAVED, title="FRONT"):
            pass
        fs = create_filesystem("acorn-dfs")
        geom = fs.geometry_grammar().parse("80t-ds")
        with reader_for(image_filepath, writable=True) as reader:
            mount = fs.open(reader, geom, surface=1)
            mount.write_bytes("$.BACK", b"second side")
            mount.set_title("REAR")
        # Side 0 untouched; side 1 holds the write.
        with reader_for(image_filepath) as reader:
            assert fs.open(reader, geom, surface=0).title == "FRONT"
        with reader_for(image_filepath) as reader:
            back = fs.open(reader, geom, surface=1)
            assert back.title == "REAR"
            assert back.read_bytes("$.BACK") == b"second side"

    def test_open_unformatted_second_side_errors_clearly(self, tmp_path):
        from oaknut.filesystem.exceptions import VolumeNotFormattedError

        # A 204800-byte image that is genuinely 80T single-sided: its
        # "side 1" under a double-sided reading is unformatted garbage.
        image_filepath = _make_dfs_image(tmp_path)  # 80T SS, 204800 bytes
        fs = create_filesystem("acorn-dfs")
        double = fs.geometry_grammar().parse("40t-ds")
        with reader_for(image_filepath) as reader:
            with pytest.raises(VolumeNotFormattedError, match=r":2"):
                fs.open(reader, double, surface=1)


class TestIdentificationEvidence:
    """`disc identify` evidence is collected from the verified signals, not a
    canned per-filesystem string — and is the same pass that gates the match.
    """

    def test_acorn_evidence_reports_catalogue_and_count(self, tmp_path):
        results = identify(_make_dfs_image(tmp_path))  # two files
        evidence = results[0].evidence
        assert any("Acorn DFS catalogue" in item for item in evidence)
        assert any("2 file" in item for item in evidence)  # dynamic, per-disc

    def test_watford_evidence_surfaces_the_verified_signals(self):
        results = identify(_watford_image_bytes(), suffix_hint=".ssd")
        evidence = results[0].evidence
        joined = "; ".join(evidence)
        assert any("0xAA marker" in item for item in evidence)
        assert any("extended catalogue" in item for item in evidence)
        # The >256KB extension-bit guard is now visible as evidence.
        assert any("extension bit" in item for item in evidence)
        # Stale wording gone — counts and sequence numbers are NOT synced.
        assert "synced metadata" not in joined
