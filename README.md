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

<p align="center">
  <img src="docs/source/_static/andalus_logo.png" width="420" height="auto" />
</p>

<h3 align="center">Applied Nuclear Data Assimilation using Least sqUareS</h5>

Applied Nuclear Data Assimilation using Least sqUareS (ANDALUS) is an Open Source data assimilation tool for improving predictions of nuclear applications.

## Features

* Perform sensitivity and uncertainty quantification using first order approximation.
* Use the Generalized Linear Least Squares equation to infer multi-group nuclear data.
* Create an adjusted ACE library.

## Documentation

Documentation can be found [here](https://daan1392.github.io/andalus/). Several example notebooks are available [here](https://daan1392.github.io/andalus/examples.html).

## Installation
To install ANDALUS with pip:
```sh
pip install andalus
```

To install the latest version (recommended):
```bash
git clone git@github.com:daan1392/andalus.git
cd andalus
pip install --editable .
```

## Acknowledgments
ANDALUS was developed as part of the ongoing PhD thesis on *Robust data assimilation for LFR nuclear data improvement* in frame of a collaboration between [SCK CEN](https://www.sckcen.be) and [ULB](http://www.ulb.ac.be).

## Author

ANDALUS was created in 2026 by Daan Houben.

* Created by **[Daan Houben](https://github.com/daan1392)**
* PyPI package: https://pypi.org/project/andalus/

Built with [Cookiecutter](https://github.com/cookiecutter/cookiecutter) and the [audreyfeldroy/cookiecutter-pypackage](https://github.com/audreyfeldroy/cookiecutter-pypackage) project template.
