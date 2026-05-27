"""Tests for the geometry layer and its grammar."""

import pytest
from oaknut.filesystem import (
    Geometry,
    GeometryError,
    GeometryGrammar,
    floppy_geometry,
    winchester_geometry,
)
from oaknut.filesystem.geometry import FLOPPY, WINCHESTER


class TestGeometryConstructors:
    def test_single_sided_floppy_size(self):
        # 80 tracks × 10 sectors × 256 bytes, single-sided.
        geom = floppy_geometry(tracks=80, sides=1)
        assert geom.image_size == 80 * 10 * 256
        assert geom.num_sectors == 800

    def test_double_sided_floppy_size(self):
        geom = floppy_geometry(tracks=80, sides=2)
        assert geom.image_size == 80 * 10 * 256 * 2
        assert geom.num_sectors == 1600

    def test_invalid_sides(self):
        with pytest.raises(GeometryError):
            floppy_geometry(tracks=80, sides=3)

    def test_winchester_size(self):
        geom = winchester_geometry(cylinders=100, heads=4, sectors_per_track=33)
        assert geom.num_sectors == 100 * 4 * 33
        assert geom.image_size == 100 * 4 * 33 * 256

    def test_empty_geometry_rejected(self):
        with pytest.raises(GeometryError):
            Geometry(surface_specs=())


class TestGeometryGrammar:
    def test_preset_lookup(self):
        small = floppy_geometry(tracks=40, sides=1, label="S")
        grammar = GeometryGrammar(presets={"s": small}, kinds=(FLOPPY,))
        assert grammar.parse("s") is small
        assert grammar.parse("S") is small  # case-insensitive
        assert grammar.preset_names() == ["s"]

    def test_parameterised_floppy(self):
        grammar = GeometryGrammar(kinds=(FLOPPY,))
        geom = grammar.parse("tracks=80,sides=2")
        assert geom.num_sectors == 1600

    def test_parameterised_floppy_sequential(self):
        grammar = GeometryGrammar(kinds=(FLOPPY,))
        interleaved = grammar.parse("tracks=80,sides=2,interleave=interleaved")
        sequential = grammar.parse("tracks=80,sides=2,interleave=sequential")
        # Same capacity, different physical layout.
        assert interleaved.num_sectors == sequential.num_sectors
        assert interleaved.surface_specs != sequential.surface_specs

    def test_parameterised_winchester(self):
        grammar = GeometryGrammar(kinds=(WINCHESTER,))
        geom = grammar.parse("cylinders=100,heads=4,spt=33")
        assert geom.num_sectors == 100 * 4 * 33

    def test_kind_not_accepted(self):
        floppy_only = GeometryGrammar(kinds=(FLOPPY,))
        with pytest.raises(GeometryError, match="hard-disc"):
            floppy_only.parse("cylinders=100,heads=4,spt=33")

    def test_unparseable_spec_lists_presets(self):
        grammar = GeometryGrammar(presets={"l": floppy_geometry(tracks=80, sides=2)})
        with pytest.raises(GeometryError, match="l"):
            grammar.parse("nonsense")

    def test_malformed_field(self):
        grammar = GeometryGrammar(kinds=(FLOPPY,))
        with pytest.raises(GeometryError, match="key=value"):
            grammar.parse("tracks 80")
