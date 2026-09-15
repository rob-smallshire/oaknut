"""Tests for the BeebSCSI / Pi1MHz ``.cfg`` extended-attributes parser."""

import pytest
from oaknut.filesystem import BeebScsiConfig, geometry_from_cfg
from oaknut.filesystem.exceptions import BeebScsiConfigError

# A minimal but realistic .cfg, close to the Pi1MHz defscsi.cfg template:
# 306 cylinders, 4 heads, 33 sectors/track, 256-byte blocks.
SAMPLE_CFG = """\
# A LUN extended attributes file
Title=BeebSCSI
Description=Reference disc

LBADescriptor=0000000000000100
ModePage0=01013204008000800001   # 0132 cyl, 04 heads
ModePage3=0315013201320006000600210100000800000000800000
ModePage4=0406000132040000
"""


class TestParseGeometry:
    def test_reads_cylinders_heads_from_page0(self):
        cfg = BeebScsiConfig.parse(SAMPLE_CFG)
        assert cfg.cylinders == 0x0132  # 306
        assert cfg.heads == 4

    def test_reads_sectors_per_track_from_page3(self):
        # The whole point of .cfg over .dsc: SPT is recorded, not assumed.
        cfg = BeebScsiConfig.parse(SAMPLE_CFG)
        assert cfg.sectors_per_track == 0x21  # 33

    def test_reads_block_size_from_lba_descriptor(self):
        cfg = BeebScsiConfig.parse(SAMPLE_CFG)
        assert cfg.block_size == 256

    def test_geometry_object(self):
        geom = BeebScsiConfig.parse(SAMPLE_CFG).geometry
        assert geom.cylinders == 306
        assert geom.heads == 4
        assert geom.sectors_per_track == 33
        assert geom.num_sectors == 306 * 4 * 33

    def test_geometry_from_cfg_convenience(self):
        geom = geometry_from_cfg(SAMPLE_CFG)
        assert geom.num_sectors == 306 * 4 * 33

    def test_non_default_spt_is_honoured(self):
        # An IDE 4x64 layout — the case a .dsc would misreport as 33.
        cfg = BeebScsiConfig.default()
        cfg.set_geometry(cylinders=100, heads=4, sectors_per_track=64)
        assert BeebScsiConfig.parse(cfg.render()).sectors_per_track == 64


class TestParseDefaults:
    def test_block_size_defaults_to_256_when_absent(self):
        cfg = BeebScsiConfig.parse("ModePage0=01000A0004008000800001\n")
        assert cfg.block_size == 256

    def test_spt_defaults_to_33_when_page3_absent(self):
        cfg = BeebScsiConfig.parse("ModePage0=01000A04008000800001\n")
        assert cfg.sectors_per_track == 33

    def test_page4_used_when_page0_absent(self):
        cfg = BeebScsiConfig.parse("ModePage4=0406000101040000\n")
        assert cfg.cylinders == 0x0101
        assert cfg.heads == 4

    def test_missing_geometry_raises(self):
        cfg = BeebScsiConfig.parse("Title=empty\n")
        with pytest.raises(BeebScsiConfigError, match="no ModePage0 or ModePage4"):
            _ = cfg.geometry


class TestSyntax:
    def test_keys_are_case_insensitive(self):
        cfg = BeebScsiConfig.parse("modepage0=01013204008000800001\n")
        assert cfg.cylinders == 0x0132

    def test_whitespace_and_equals_separators(self):
        cfg = BeebScsiConfig.parse("ModePage0  =  01013204008000800001\n")
        assert cfg.cylinders == 0x0132

    def test_hex_0x_prefix_tolerated(self):
        cfg = BeebScsiConfig.parse("ModePage0=0x01013204008000800001\n")
        assert cfg.cylinders == 0x0132

    def test_unknown_key_ignored(self):
        cfg = BeebScsiConfig.parse("Nonsense=1234\nModePage0=01013204008000800001\n")
        assert cfg.cylinders == 0x0132

    def test_title_and_description(self):
        cfg = BeebScsiConfig.parse(SAMPLE_CFG)
        assert cfg.title == "BeebSCSI"
        assert cfg.description == "Reference disc"

    def test_malformed_hex_line_ignored(self):
        # Odd digit count -> line kept verbatim, key not registered.
        cfg = BeebScsiConfig.parse("ModePage3=012\nModePage0=01013204008000800001\n")
        assert cfg.sectors_per_track == 33  # ModePage3 not registered


class TestRoundTrip:
    def test_preserves_comments_and_unknown_lines(self):
        text = "# a comment\nNonsense=keepme\nTitle=Kept\n"
        rendered = BeebScsiConfig.parse(text).render()
        assert "# a comment" in rendered
        assert "Nonsense=keepme" in rendered

    def test_unchanged_file_renders_identically(self):
        assert BeebScsiConfig.parse(SAMPLE_CFG).render() == SAMPLE_CFG

    def test_render_is_idempotent(self):
        once = BeebScsiConfig.parse(SAMPLE_CFG).render()
        twice = BeebScsiConfig.parse(once).render()
        assert once == twice

    def test_set_geometry_survives_round_trip(self):
        cfg = BeebScsiConfig.default()
        cfg.set_geometry(cylinders=296, heads=6, sectors_per_track=33)
        reparsed = BeebScsiConfig.parse(cfg.render())
        assert reparsed.cylinders == 296
        assert reparsed.heads == 6
        assert reparsed.sectors_per_track == 33
        assert reparsed.block_size == 256

    def test_inline_comment_preserved_when_geometry_changed(self):
        cfg = BeebScsiConfig.parse(SAMPLE_CFG)
        cfg.set_geometry(cylinders=10, heads=2, sectors_per_track=33)
        rendered = cfg.render()
        assert "# 0132 cyl, 04 heads" in rendered
        assert BeebScsiConfig.parse(rendered).cylinders == 10


class TestDefault:
    def test_default_is_wellformed(self):
        cfg = BeebScsiConfig.default()
        cfg.set_geometry(cylinders=50, heads=4, sectors_per_track=33)
        geom = BeebScsiConfig.parse(cfg.render()).geometry
        assert geom.num_sectors == 50 * 4 * 33

    def test_set_geometry_rejects_nonpositive(self):
        cfg = BeebScsiConfig.default()
        with pytest.raises(BeebScsiConfigError, match="positive"):
            cfg.set_geometry(cylinders=0, heads=4, sectors_per_track=33)
