"""Fragment sharing on New Map discs.

FileCore packs several small files into one fragment (each addressed by a
sector offset in its indirect address) instead of giving every small file
its own minimum-size fragment. Sharing only helps when the minimum
fragment is larger than a sector — true on E (2048-byte minimum, 1024-byte
sector), not on F (both 1024). The fragment is freed only when its last
sharer is removed.
"""

from __future__ import annotations

from oaknut.adfs.adfs import ADFS, ADFS_E, ADFS_F


def _addr(path):
    _, entry = path._resolve()
    return entry.indirect_disc_address


def test_small_files_share_a_fragment():
    adfs = ADFS.create(ADFS_E, title="ShareE")
    try:
        payloads = {f"S{i}": bytes([i]) * (400 + i * 50) for i in range(6)}  # all < 1024
        for name, data in payloads.items():
            (adfs.root / name).write_bytes(data)
        assert adfs.validate() == []
        fids = {(_addr(adfs.root / n) >> 8) for n in payloads}
        assert len(fids) < len(payloads), "small files should share fragments"
        for name, data in payloads.items():
            assert (adfs.root / name).read_bytes() == data
    finally:
        adfs.close()


def test_shared_fragment_kept_until_last_sharer_removed():
    adfs = ADFS.create(ADFS_E, title="ShareLife")
    try:
        (adfs.root / "A").write_bytes(b"a" * 500)
        (adfs.root / "B").write_bytes(b"b" * 500)
        # A and B share one fragment.
        assert (_addr(adfs.root / "A") >> 8) == (_addr(adfs.root / "B") >> 8)
        free_two = adfs.free_space

        (adfs.root / "A").unlink()  # a sharer goes; fragment stays for B
        assert adfs.validate() == []
        assert adfs.free_space == free_two, "fragment must not be freed while B shares it"
        assert (adfs.root / "B").read_bytes() == b"b" * 500

        (adfs.root / "B").unlink()  # last sharer goes; fragment is freed
        assert adfs.validate() == []
        assert adfs.free_space > free_two
        assert list(adfs.root.iterdir()) == []
    finally:
        adfs.close()


def test_sharing_survives_reopen(tmp_path):
    image = tmp_path / "e.adf"
    with ADFS.create_file(image, ADFS_E, title="ShareRT") as adfs:
        for i in range(6):
            (adfs.root / f"S{i}").write_bytes(bytes([i]) * 500)
    with ADFS.from_file(image) as adfs:
        assert adfs.validate() == []
        fids = {(_addr(adfs.root / f"S{i}") >> 8) for i in range(6)}
        assert len(fids) < 6
        for i in range(6):
            assert (adfs.root / f"S{i}").read_bytes() == bytes([i]) * 500


def test_overwrite_shared_file():
    adfs = ADFS.create(ADFS_E, title="OverShare")
    try:
        (adfs.root / "A").write_bytes(b"a" * 500)
        (adfs.root / "B").write_bytes(b"b" * 500)
        (adfs.root / "A").write_bytes(b"A" * 700)  # overwrite a sharer
        assert adfs.validate() == []
        assert (adfs.root / "A").read_bytes() == b"A" * 700
        assert (adfs.root / "B").read_bytes() == b"b" * 500
    finally:
        adfs.close()


def test_large_files_do_not_share():
    adfs = ADFS.create(ADFS_E, title="NoShare")
    try:
        # Files >= (min_fragment - sector) get their own fragments.
        for i in range(4):
            (adfs.root / f"L{i}").write_bytes(bytes([i]) * 1500)
        assert adfs.validate() == []
        fids = {(_addr(adfs.root / f"L{i}") >> 8) for i in range(4)}
        assert len(fids) == 4, "large files should each own a fragment"
    finally:
        adfs.close()


def test_f_format_does_not_share():
    """On F the minimum fragment is one sector, so there is no room to share."""
    adfs = ADFS.create(ADFS_F, title="NoShareF")
    try:
        for i in range(5):
            (adfs.root / f"S{i}").write_bytes(bytes([i]) * 300)
        assert adfs.validate() == []
        fids = {(_addr(adfs.root / f"S{i}") >> 8) for i in range(5)}
        assert len(fids) == 5, "F cannot share (min fragment == sector)"
        for i in range(5):
            assert (adfs.root / f"S{i}").read_bytes() == bytes([i]) * 300
    finally:
        adfs.close()
