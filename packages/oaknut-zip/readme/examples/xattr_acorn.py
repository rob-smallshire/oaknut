"""Extended attributes in the user.acorn.* namespace."""

from cli_example_helper import show_xattrs, silent

silent("oaknut-zip extract --meta-format xattr-acorn NetUtils.zip -d .")
show_xattrs("SetStation")
print()
show_xattrs("ReadMe")
