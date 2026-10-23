"""Writing and reading a BBC BASIC data file."""

from oaknut.basic import datafile

with datafile.open("scores.dat", "w") as f:
    f.write("ALICE")  # str   -> string record
    f.write(42)  # int   -> integer record
    f.write(3.5)  # float -> real record

with datafile.open("scores.dat", "r") as f:
    for value in f:
        print(repr(value))
