"""Validating a disc's structure."""

from oaknut.adfs import ADFS

with ADFS.from_file("disc.adf") as adfs:
    errors = adfs.validate()
    print(errors)
