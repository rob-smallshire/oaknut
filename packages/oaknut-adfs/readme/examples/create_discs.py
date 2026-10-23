"""Creating New-map floppy images."""

from oaknut.adfs import ADFS, ADFS_E, ADFS_F_PLUS

# An 800 KB New-map E disc.
with ADFS.create_file("disc.adf", ADFS_E, title="RISCOS") as adfs:
    (adfs.root / "$.ReadMe").write_bytes(
        b"oaknut-adfs demo", load_address=0xFFFFFF00, exec_address=0x00000000
    )
    (adfs.root / "$.Apps").mkdir()

# A 1600 KB F+ disc, whose Big directories allow long filenames.
with ADFS.create_file("big.adf", ADFS_F_PLUS, title="Extended") as adfs:
    (adfs.root / "$.AVeryLongFileNameIndeed").write_bytes(b"...")

for filename in ("disc.adf", "big.adf"):
    with ADFS.from_file(filename) as adfs:
        print(filename, adfs.title, [entry.name for entry in (adfs.root / "$").iterdir()])
