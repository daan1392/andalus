# ANDALUS

![PyPI version](https://img.shields.io/pypi/v/andalus.svg)

Applied Nuclear Data Assimilation using Least sqUareS (ANDALUS) is an Open Source data assimilation tool for improving predictions of nuclear applications.

* Created by **[Daan Houben](https://github.com/daan1392)**
  * PyPI: https://pypi.org/user/daan1392/
* PyPI package: https://pypi.org/project/andalus/
* Free software: MIT License

## Features

* TODO

## Documentation

Documentation is built with [Zensical](https://zensical.org/) and deployed to GitHub Pages.

* **Live site:** https://daan1392.github.io/andalus/
* **Preview locally:** `just docs-serve` (serves at http://localhost:8000)
* **Build:** `just docs-build`

API documentation is auto-generated from docstrings using [mkdocstrings](https://mkdocstrings.github.io/).

Docs deploy automatically on push to `main` via GitHub Actions. To enable this, go to your repo's Settings > Pages and set the source to **GitHub Actions**.

## Development

To set up for local development:

```bash
# Clone your fork
git clone git@github.com:your_username/andalus.git
cd andalus

# Install in editable mode with live updates
uv tool install --editable .
```

This installs the CLI globally but with live updates - any changes you make to the source code are immediately available when you run `andalus`.

Run tests:

```bash
uv run pytest
```

Run quality checks (format, lint, type check, test):

```bash
just qa
```

## Author

ANDALUS was created in 2026 by Daan Houben.

Built with [Cookiecutter](https://github.com/cookiecutter/cookiecutter) and the [audreyfeldroy/cookiecutter-pypackage](https://github.com/audreyfeldroy/cookiecutter-pypackage) project template.
