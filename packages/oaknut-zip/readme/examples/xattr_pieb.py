"""Extended attributes in PiEconetBridge's user.econet_* namespace."""

from cli_example_helper import show_xattrs, silent

silent("oaknut-zip extract --meta-format xattr-pieb NetUtils.zip -d .")
show_xattrs("SetStation")
print()
show_xattrs("ReadMe")
