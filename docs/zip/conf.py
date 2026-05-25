"""Sphinx configuration for the oaknut zip manual.

Generic settings — theme, the common extension set, autodoc /
intersphinx / napoleon defaults, and the shared static assets — come
from ``docs/_shared/conf_base.py`` via the star-import below. This file
only names the body; zip-specific extensions can be appended here later.
"""

import sys
from pathlib import Path

# Shared base config: extensions, theme, html_static_path, and the
# autodoc / intersphinx / napoleon defaults common to every body.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_shared"))
from conf_base import *  # noqa: E402, F403

project = "oaknut zip"
html_title = "oaknut zip"
