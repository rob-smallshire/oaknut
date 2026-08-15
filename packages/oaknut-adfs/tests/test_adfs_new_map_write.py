"""Writing files and directories into a New Map (ADFS E) disc.

Exercises the single-zone FreeLink allocator: allocate/free fragments,
rebuild the bitmap and free chain, and keep the zone check, directory
check bytes and free-space accounting self-consistent. Validation is by
round-trip — everything written is read back and the disc validates.
"""

from __future__ import annotations

from oaknut.adfs.adfs import ADFS, ADFS_E
from oaknut.adfs.exceptions import ADFSError


def _fresh_e():
    return ADFS.create(ADFS_E, title="WriteE")


def test_write_and_read_single_file():
    adfs = _fresh_e()
    try:
        (adfs.root / "Hello").write_bytes(b"Hello, Acorn world!", load_address=0x8000)
        assert adfs.validate() == []
        data = (adfs.root / "Hello").read_bytes()
        assert data == b"Hello, Acorn world!"
        assert (adfs.root / "Hello").stat().load_address == 0x8000
    finally:
        adfs.close()


def test_write_multiple_files_all_read_back():
    adfs = _fresh_e()
    try:
        payloads = {
            "Small": b"x",
            "Medium": bytes(range(256)) * 4,  # 1024 bytes
            "Large": bytes((i * 7) & 0xFF for i in range(5000)),
        }
        for name, data in payloads.items():
            (adfs.root / name).write_bytes(data)
        assert adfs.validate() == []
        assert {p.name for p in adfs.root.iterdir()} == set(payloads)
        for name, data in payloads.items():
            assert (adfs.root / name).read_bytes() == data
    finally:
        adfs.close()


def test_mkdir_and_write_nested_file():
    adfs = _fresh_e()
    try:
        (adfs.root / "Games").mkdir()
        assert (adfs.root / "Games").is_dir()
        (adfs.root / "Games" / "Elite").write_bytes(b"COMMANDER JAMESON")
        assert adfs.validate() == []
        assert (adfs.root / "Games" / "Elite").read_bytes() == b"COMMANDER JAMESON"
        # The subdirectory kept the New Map "Nick" signature, not "Hugo".
        raw = bytes(adfs._disc.sector_range(0, ADFS_E.total_sectors))
        games_addr = adfs._object_disc_sector((adfs.root / "Games")._resolve()[1].indirect_disc_address)
        assert raw[games_addr * 256 + 1 : games_addr * 256 + 5] == b"Nick"
    finally:
        adfs.close()


def test_delete_file_frees_space():
    adfs = _fresh_e()
    try:
        before = adfs.free_space
        (adfs.root / "Temp").write_bytes(bytes(4000))
        assert adfs.free_space < before
        (adfs.root / "Temp").unlink()
        assert adfs.validate() == []
        assert adfs.free_space == before
        assert list(adfs.root.iterdir()) == []
    finally:
        adfs.close()


def test_overwrite_file_reuses_space():
    adfs = _fresh_e()
    try:
        (adfs.root / "F").write_bytes(bytes(3000))
        mid = adfs.free_space
        (adfs.root / "F").write_bytes(bytes(3000))  # same size — free then realloc
        assert adfs.free_space == mid
        assert adfs.validate() == []
    finally:
        adfs.close()


def test_in_place_edits_keep_nick_signature():
    adfs = _fresh_e()
    try:
        (adfs.root / "A").write_bytes(b"data")
        adfs.root.title = "Retitled"
        (adfs.root / "A").rename("B")
        assert adfs.validate() == []
        assert adfs.root.title == "Retitled"
        assert {p.name for p in adfs.root.iterdir()} == {"B"}
        raw = bytes(adfs._disc.sector_range(0, ADFS_E.total_sectors))
        assert raw[0x801:0x805] == b"Nick"  # root not flipped to Hugo
    finally:
        adfs.close()


def test_write_survives_close_and_reopen(tmp_path):
    image = tmp_path / "e.adf"
    with ADFS.create_file(image, ADFS_E, title="Persist") as adfs:
        (adfs.root / "Doc").write_bytes(b"persisted content")
        (adfs.root / "Sub").mkdir()
        (adfs.root / "Sub" / "Inner").write_bytes(b"inner")

    with ADFS.from_file(image) as adfs:
        assert adfs.validate() == []
        assert (adfs.root / "Doc").read_bytes() == b"persisted content"
        assert (adfs.root / "Sub" / "Inner").read_bytes() == b"inner"


def test_write_basic_roundtrips():
    adfs = _fresh_e()
    try:
        (adfs.root / "Prog").write_basic('10 PRINT "HI"\n20 END\n')
        assert adfs.validate() == []
        assert 'PRINT "HI"' in (adfs.root / "Prog").read_basic()
    finally:
        adfs.close()


def test_many_files_then_delete_alternate():
    """Stress the allocator: fill, then free every other file, leaving holes."""
    adfs = _fresh_e()
    try:
        names = [f"File{i:02d}" for i in range(10)]
        for i, name in enumerate(names):
            (adfs.root / name).write_bytes(bytes([i]) * (500 + i * 100))
        assert adfs.validate() == []
        for name in names[::2]:
            (adfs.root / name).unlink()
        assert adfs.validate() == []
        # Remaining files still read correctly despite the free-space holes.
        for i, name in enumerate(names):
            if i % 2 == 1:
                assert (adfs.root / name).read_bytes() == bytes([i]) * (500 + i * 100)
    finally:
        adfs.close()
