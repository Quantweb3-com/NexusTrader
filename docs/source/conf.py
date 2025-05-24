# Configuration file for Sphinx documentation

import os
import sys

# sys.path.insert(0, os.path.abspath("."))
# sys.path.insert(0, os.path.abspath("../"))
sys.path.insert(0, os.path.abspath("../.."))

project = "NexusTrader"
copyright = "2024, River Trading"
author = "River Trading"

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx_autodoc_typehints",
    "sphinx.ext.todo",
    "myst_parser",
    "sphinx.ext.ifconfig",
    "sphinx.ext.mathjax",  # For HTML math, good to have
]

latex_engine = "xelatex"

templates_path = ["_templates"]
exclude_patterns = []

html_theme = "furo"
html_static_path = ["_static"]
html_theme_options = {
    "light_logo": "logo-light-crop.png",
    "dark_logo": "logo-dark-crop.png",
}

# Napoleon settings
napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = True
napoleon_include_private_with_doc = True

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

# Todo settings
todo_include_todos = True

# Mock modules that might cause import issues
autodoc_mock_imports = [
    "aiohttp",
    "redis",
    "aioredis",
    "ccxt",
    "ccxt.pro",
    "dynaconf",
    "spdlog",
    "nautilus_trader",
    "orjson",
    "aiosqlite",
    "aiolimiter",
    "returns",
    "picows",
    "apscheduler",
    "zmq",
    "certifi",
    "bcrypt",
    "pathlib",
]

# Docutils settings
docutils_tab_width = 4
docutils_no_indent = True
