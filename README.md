<p align="center">
  <img src="https://img.shields.io/pypi/v/andalus.svg" />
  <a href="https://github.com/daan1392/andalus/actions/workflows/ci.yml">
    <img src="https://github.com/daan1392/andalus/actions/workflows/ci.yml/badge.svg" />
  </a>
  <img src="https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue" />
  <a href="https://codecov.io/gh/daan1392/andalus">
    <img src="https://codecov.io/gh/daan1392/andalus/graph/badge.svg" />
  </a>
</p>

<h1 align="center">ANDALUS</h1>


<h3 align="center">Applied Nuclear Data Assimilation using Least sqUareS</h5>

Applied Nuclear Data Assimilation using Least sqUareS (ANDALUS) is an Open Source data assimilation tool for improving predictions of nuclear applications.

* Created by **[Daan Houben](https://github.com/daan1392)**
  * PyPI: https://pypi.org/user/daan1392/
* PyPI package: https://pypi.org/project/andalus/

## Features

* Perform sensitivity and uncertainty quantification suing first order approximation.
* Use the Generalized Linear Least Squares equation to infer multi-group nuclear data.

## Documentation

Documentation is built with [Sphynx](https://www.sphinx-doc.org) and deployed to GitHub Pages.

* **Live site:** https://daan1392.github.io/andalus/
* **Preview locally:** `just docs-serve` (serves at http://localhost:8000)
* **Build:** `just docs-build`

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
