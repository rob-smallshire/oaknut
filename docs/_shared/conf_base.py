"""Shared Sphinx configuration for every oaknut documentation body.

Each ``docs/<body>/conf.py`` does ``from conf_base import *`` and then
overrides the body-specific settings (``project``, ``html_title``) and
appends any body-specific extensions. Only genuinely cross-body
settings belong here — theme, the common extension set, autodoc and
intersphinx defaults, and the shared static assets. Body-specific
machinery (the disc manual's ``cli-example`` / ``oaknut-command``
directives, for instance) stays in that body's own ``conf.py``.
"""

from pathlib import Path

author = "Robert Smallshire"
copyright = "2024-2026, Robert Smallshire"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx.ext.napoleon",
    "sphinx_copybutton",
    "sphinx_design",
]

# Google-style docstrings — Args:/Returns:/Raises: sections.
napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False
napoleon_use_rtype = False
napoleon_use_param = False

html_theme = "sphinx_clarity_theme"

# Static assets live once under docs/_shared/_static and are shared by
# every body. The absolute path lets each body's conf.py — which sits at
# a different depth — pick them up without a relative ../ dance.
# _static/platform-tabs.js auto-selects the host-platform tab in
# sphinx-design tab-sets keyed on the :sync: IDs bash / zsh / powershell.
html_static_path = [str((Path(__file__).resolve().parent / "_static"))]
html_js_files = ["platform-tabs.js"]
html_css_files = ["font-size.css"]

autodoc_member_order = "bysource"
autodoc_typehints = "description"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

exclude_patterns = ["_build"]

# Suppress warnings from star-aliases (*CAT etc.) in Click docstrings
# that sphinx-click renders — the * is misinterpreted as RST emphasis.
suppress_warnings = ["docutils"]
