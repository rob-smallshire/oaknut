"""ADFS Filetyped / Datestamped capability tests.

On ADFS both live inside the 32-bit load/exec fields under the 0xFFF
marker, so setting one must preserve the other, and adopting the marker
on a previously-addressed file uses deterministic defaults.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from oaknut.adfs import ADFS, ADFS_S
from oaknut.filesystem import (
    Datestamped,
    Filetyped,
    create_filesystem,
    reader_for,
)

_WHEN = datetime(2024, 3, 1, 14, 22, 8, 50_000)


def _make_image(tmp_path):
    image_filepath = tmp_path / "test.ads"
    with ADFS.create_file(str(image_filepath), ADFS_S, title="TESTDISC") as adfs:
        # A plain addressed file (BBC default load/exec).
        (adfs.root / "$.PLAIN").write_bytes(
            b"plain", load_address=0x1900, exec_address=0x8023
        )
    return image_filepath


def _mount(image_filepath, *, writable=False):
    filesystem = create_filesystem("adfs")
    reader = reader_for(image_filepath, writable=writable).__enter__()
    mount = filesystem.open(reader, filesystem.probe(reader).geometry)
    return reader, mount


class TestCapabilities:
    def test_mount_provides_both(self, tmp_path):
        reader, mount = _mount(_make_image(tmp_path))
        try:
            assert isinstance(mount, Filetyped)
            assert isinstance(mount, Datestamped)
        finally:
            reader.__exit__(None, None, None)

    def test_resolution_is_centiseconds(self, tmp_path):
        reader, mount = _mount(_make_image(tmp_path))
        try:
            assert mount.datestamp_resolution == timedelta(milliseconds=10)
        finally:
            reader.__exit__(None, None, None)


class TestEqualLoadExecIsAddressPair:
    """A marker-bearing file whose load equals its exec is a plain address,
    per RISC OS FileSwitch — not a filetype/datestamp (the case that would
    otherwise decode to a spurious 1900–1901 date)."""

    def _make_equal_pair_image(self, tmp_path):
        image_filepath = tmp_path / "pair.ads"
        with ADFS.create_file(str(image_filepath), ADFS_S, title="PAIR") as adfs:
            # A module load address, top twelve bits 0xFFF, load == exec.
            (adfs.root / "$.MODULE").write_bytes(
                b"module", load_address=0xFFFFFA00, exec_address=0xFFFFFA00
            )
        return image_filepath

    def test_filetype_and_datestamp_read_none(self, tmp_path):
        reader, mount = _mount(self._make_equal_pair_image(tmp_path))
        try:
            assert mount.filetype("$.MODULE") is None
            assert mount.datestamp("$.MODULE") is None
        finally:
            reader.__exit__(None, None, None)


class TestPlainFile:
    def test_unstamped_reads_none(self, tmp_path):
        reader, mount = _mount(_make_image(tmp_path))
        try:
            assert mount.filetype("$.PLAIN") is None
            assert mount.datestamp("$.PLAIN") is None
        finally:
            reader.__exit__(None, None, None)


class TestSetFiletype:
    def test_round_trips_and_defaults_date_to_epoch(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_filetype("$.PLAIN", 0xFFB)  # BASIC
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.filetype("$.PLAIN") == 0xFFB
            # Un-stamped before, so the date is the deterministic epoch.
            assert mount.datestamp("$.PLAIN") == datetime(1900, 1, 1)
        finally:
            reader.__exit__(None, None, None)


class TestSetDatestamp:
    def test_round_trips_and_defaults_type_to_data(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_datestamp("$.PLAIN", _WHEN)
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.datestamp("$.PLAIN") == _WHEN
            # Un-stamped before, so the filetype defaults to Data (&FFD).
            assert mount.filetype("$.PLAIN") == 0xFFD
        finally:
            reader.__exit__(None, None, None)


class TestOrthogonalPreservation:
    def test_set_filetype_preserves_date(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_datestamp("$.PLAIN", _WHEN)
            mount.set_filetype("$.PLAIN", 0xFEB)  # Obey, date must survive
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.filetype("$.PLAIN") == 0xFEB
            assert mount.datestamp("$.PLAIN") == _WHEN
        finally:
            reader.__exit__(None, None, None)

    def test_set_datestamp_preserves_filetype(self, tmp_path):
        path = _make_image(tmp_path)
        reader, mount = _mount(path, writable=True)
        try:
            mount.set_filetype("$.PLAIN", 0xFF9)  # Sprite
            later = datetime(2090, 6, 1, 9, 0, 0)
            mount.set_datestamp("$.PLAIN", later)
        finally:
            reader.__exit__(None, None, None)
        reader, mount = _mount(path)
        try:
            assert mount.filetype("$.PLAIN") == 0xFF9
            assert mount.datestamp("$.PLAIN") == datetime(2090, 6, 1, 9, 0, 0)
        finally:
            reader.__exit__(None, None, None)


# --- New Map formats (New and Big directories) and the RISC OS corpus -------

import pytest  # noqa: E402
from oaknut.adfs import (  # noqa: E402
    ADFS_E,
    ADFS_E_PLUS,
    ADFS_F,
    ADFS_F_PLUS,
    ADFS_G,
    ADFS_G_PLUS,
)

from tests.fixtures import REFERENCE_IMAGES_DIRPATH  # noqa: E402

_RISCOS_DIRPATH = REFERENCE_IMAGES_DIRPATH / "adfs-riscos"


class TestNewMapFiletypeDatestamp:
    """Filetype/datestamp must round-trip on every New Map layout.

    New directories (E/F/G) and Big directories (E+/F+/G+) serialise their
    entries differently, and multi-zone discs place the map mid-disc, so each
    combination exercises a distinct write path for the 32-bit load/exec fields.
    """

    @pytest.mark.parametrize(
        "fmt",
        [ADFS_E, ADFS_F, ADFS_G, ADFS_E_PLUS, ADFS_F_PLUS, ADFS_G_PLUS],
        ids=["E", "F", "G", "E+", "F+", "G+"],
    )
    def test_round_trips_and_disc_stays_valid(self, fmt, tmp_path):
        image_filepath = tmp_path / "typed.adf"
        with ADFS.create_file(str(image_filepath), fmt, title="TYPED") as adfs:
            (adfs.root / "$.TypedFile").write_bytes(
                b"payload", load_address=0x1900, exec_address=0x8023
            )

        when = datetime(1995, 6, 15, 12, 30, 45, 100_000)
        reader, mount = _mount(image_filepath, writable=True)
        try:
            assert isinstance(mount, Filetyped) and isinstance(mount, Datestamped)
            mount.set_filetype("$.TypedFile", 0xFFB)  # BASIC
            mount.set_datestamp("$.TypedFile", when)
        finally:
            reader.__exit__(None, None, None)

        reader, mount = _mount(image_filepath)
        try:
            assert mount.filetype("$.TypedFile") == 0xFFB
            assert mount.datestamp("$.TypedFile") == when
        finally:
            reader.__exit__(None, None, None)

        # The metadata write must not damage the New Map structures.
        with ADFS.from_file(image_filepath, read_only=True) as adfs:
            assert adfs.is_new_map
            assert adfs.validate() == []


class TestRiscOsCorpusMetadata:
    """The shipped RISC OS specimens carry genuine filetypes and datestamps."""

    def test_new_map_e_disc_decodes_known_metadata(self):
        # E_RISCOS310_NewLook !RunImage is BASIC (&FFB), stamped 1993-03-15.
        reader, mount = _mount(_RISCOS_DIRPATH / "E_RISCOS310_NewLook.adf")
        try:
            path = "$.!NewLook.!RunImage"
            assert mount.filetype(path) == 0xFFB
            assert mount.datestamp(path) == datetime(1993, 3, 15, 13, 47, 27, 210_000)
        finally:
            reader.__exit__(None, None, None)

    def test_old_map_new_directory_d_disc_decodes_metadata(self):
        # D_RISCOS310_App1 !Configure.!RunImage is Absolute (&FF8).
        reader, mount = _mount(_RISCOS_DIRPATH / "D_RISCOS310_App1.adf")
        try:
            assert mount.filetype("$.!Configure.!RunImage") == 0xFF8
            stamp = mount.datestamp("$.!Configure.!RunImage")
            assert stamp is not None and stamp.year == 1988
        finally:
            reader.__exit__(None, None, None)

    def test_corpus_filetype_follows_the_fileswitch_rule(self):
        # A broad sweep: a file is typed exactly when it carries the marker
        # AND load != exec. These are RISC OS application discs, so the vast
        # majority are typed; the exceptions are load == exec address pairs
        # (e.g. a module load address like &FFFFFA00/&FFFFFA00).
        from oaknut.file.datestamp import is_datestamped

        for image in (
            "D_Arthur_Welcome.adf",
            "D_RISCOS310_App1.adf",
            "E_RISCOS310_NewLook.adf",
        ):
            reader, mount = _mount(_RISCOS_DIRPATH / image)
            try:

                def walk(path):
                    for entry in mount.iter_entries(path):
                        if entry.is_dir:
                            yield from walk(entry.path)
                        else:
                            yield entry.path

                files = list(walk("$"))
                assert files, image
                for path in files:
                    meta = mount.acorn_meta(path)
                    expected = is_datestamped(meta.load_address, meta.exec_address)
                    assert (mount.filetype(path) is not None) == expected, (image, path)
                    assert (mount.datestamp(path) is not None) == expected, (image, path)
                typed = sum(1 for f in files if mount.filetype(f) is not None)
                assert typed >= len(files) * 3 // 4, (image, typed, len(files))
            finally:
                reader.__exit__(None, None, None)
