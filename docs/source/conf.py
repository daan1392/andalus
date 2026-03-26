# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

project = "ANDALUS"
copyright = "2026, Daan Houben"
author = "Daan Houben"
release = "0.1.1"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # Core library to read docstrings
    "sphinx.ext.napoleon",  # Supports Google/NumPy style docstrings
    "sphinx.ext.viewcode",  # Adds links to the highlighted source code
    "myst_parser",  # Markdown support
    "nbsphinx",  # Jupyter Notebook support
    "sphinx.ext.mathjax",  # For rendering formulas in notebooks
    "sphinx_collections",  # For collecting examples and tutorials
]

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

myst_enable_extensions = [
    "dollarmath",
    "amsmath",
]

collections = {
    "examples_gallery": {
        "driver": "copy_folder",
        "source": "examples/",
        "target": "examples/",
        "ignore": ["*.py", ".sh"],
    }
}

collections_final_clean = False

python_use_unqualified_type_names = True

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "**.ipynb_checkpoints"]


# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = "pydata_sphinx_theme"
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_logo = "_static/data-assimilation.png"
html_favicon = "_static/data-assimilation.png"

# def setup(app):
#     app.add_css_file('custom.css')
