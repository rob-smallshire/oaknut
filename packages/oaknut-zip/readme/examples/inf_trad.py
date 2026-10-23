"""Traditional .inf sidecars written by the default extraction."""

from cli_example_helper import show, silent

silent("oaknut-zip extract NetUtils.zip -d .")
show("cat SetStation.inf")
print()
show("cat ReadMe.inf")
