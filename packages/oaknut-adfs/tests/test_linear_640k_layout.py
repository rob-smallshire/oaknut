"""A 640K ADFS image laid out in linear logical-sector order.

640K ADFS-L floppies are normally imaged with the two sides interleaved
per track (the ``.adl`` convention BeebEm and other emulators emit). But
some 640K images are laid out in plain logical-sector order — sector N at
byte N x 256 — with no side interleave. ``BCPL.adf`` (sourced from a
Stardot forum thread) is one such image.

Both layouts share the same size, and the root directory plus free-space
map live entirely in track 0 side 0, where the two layouts coincide. The
two only diverge once a directory's sectors cross a track boundary — so
``$`` reads identically either way and only a descent into a deeper
directory exposes the difference. Treating this image as interleaved
mangles ``$.Library`` (its fifth sector, logical sector 16, lands at byte
0x2000 instead of 0x1000), yielding a directory tail of ``faul``.
"""

from oaknut.adfs import ADFS

from tests.fixtures import REFERENCE_IMAGES_DIRPATH

_BCPL = REFERENCE_IMAGES_DIRPATH / "adfs-linear" / "BCPL.adf"


class TestLinear640kLayout:
    def test_root_lists_top_level_entries(self):
        # The root is interleave-immune, so this works even today.
        with ADFS.from_file(_BCPL) as adfs:
            names = sorted(entry.name for entry in adfs.root)
        assert names == ["ALib", "Library", "ReadMe"]

    def test_descends_into_subdirectory_crossing_a_track_boundary(self):
        # $.Library spans logical sectors 12-16; sector 16 is the first
        # sector of track 1, where interleaved and linear layouts diverge.
        with ADFS.from_file(_BCPL) as adfs:
            library = adfs.root / "Library"
            names = sorted(entry.name for entry in library)
        assert names == ["bcpl", "join"]

    def test_walks_the_whole_tree(self):
        # A deep file (ALib.Lib.xmap) lives at logical sector 154,
        # well past the first track boundary.
        found = []

        def walk(directory):
            for entry in directory:
                if entry.is_dir():
                    walk(entry)
                else:
                    found.append(str(entry))

        with ADFS.from_file(_BCPL) as adfs:
            walk(adfs.root)

        assert "$.ALib.Lib.xmap" in found


_ARC_03 = REFERENCE_IMAGES_DIRPATH / "adfs-8bs" / "arc-03.640.adf"


class TestDamagedDiscLayout:
    """A damaged disc that neither layout reads in full.

    ARC-03 is interleaved, but three of its subdirectories were lost from
    the disc, so no layout walks its whole tree. The ``.adf`` suffix leans
    linear, yet the interleaved layout reads eight of its directories to the
    linear layout's two, and the layout that reads more of the tree is the
    one the disc was written in.
    """

    def test_keeps_the_layout_that_reads_more_of_the_tree(self):
        with ADFS.from_file(_ARC_03, read_only=True) as adfs:
            # $.!Bank's sectors lie past track 0, where the layouts diverge.
            names = sorted(entry.name for entry in adfs.root / "!Bank")
        assert names == ["!Boot", "!Run", "!Runimage", "!SpriteS", "Template"]

    def test_validate_reports_only_the_lost_subdirectories_and_the_stale_root(self):
        with ADFS.from_file(_ARC_03, read_only=True) as adfs:
            paths = sorted(str(finding).split(":")[0] for finding in adfs.validate())
        assert paths == ["$", "$.!Warfarin", "$.!Xchanger", "$.Music"]
