"""PiEconetBridge .inf sidecars, which end without a newline."""

from cli_example_helper import show, silent

silent("oaknut-zip extract --meta-format inf-pieb NetUtils.zip -d .")
show("cat SetStation.inf")
print()
show("cat ReadMe.inf")
