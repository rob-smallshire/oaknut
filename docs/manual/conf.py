"""Sphinx configuration for oaknut documentation."""

project = "oaknut"
author = "Robert Smallshire"
copyright = "2024-2026, Robert Smallshire"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.doctest",
    "sphinx.ext.intersphinx",
    "sphinx_click",
    "sphinx_copybutton",
    "sphinx_design",
]

# Theme
html_theme = "sphinx_clarity_theme"
html_title = "oaknut"

# Autodoc
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Source
exclude_patterns = ["_build"]

# Suppress warnings from star-aliases (*CAT etc.) in Click docstrings
# that sphinx-click renders — the * is misinterpreted as RST emphasis.
suppress_warnings = ["docutils"]
