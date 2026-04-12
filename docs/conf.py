"""Sphinx configuration for oaknut documentation."""

project = "oaknut"
author = "Robert Smallshire"
copyright = "2024-2026, Robert Smallshire"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx_click",
    "sphinx_copybutton",
]

# Theme
html_theme = "furo"
html_title = "oaknut"

# Autodoc
autodoc_member_order = "bysource"
autodoc_typehints = "description"

# Intersphinx
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# Source
exclude_patterns = [
    "readme_examples",
    "README.md.j2",
    "_build",
]

# Suppress warnings from star-aliases (*CAT etc.) in Click docstrings
# that sphinx-click renders — the * is misinterpreted as RST emphasis.
suppress_warnings = ["docutils"]
