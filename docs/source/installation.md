# Installation

## Prerequisites

ANDALUS requires **Python 3.10 or later**. The following dependencies are installed automatically:

| Package | Purpose |
| --- | --- |
| `pandas` | Core data structures for sensitivities and covariances |
| `numpy` | Numerical operations |
| `serpentTools` | Reading Serpent Monte Carlo output files |
| `sandy` | Reading ERRORR covariance files and exporting to ACE format |
| `pyyaml` | Parsing YAML configuration files |
| `tables` | HDF5 storage via `pandas.HDFStore` |

## Stable release

Install the latest published version from PyPI:

```sh
pip install andalus
```

If you prefer [`uv`](https://docs.astral.sh/uv/):

```sh
uv add andalus
```

## From source

Clone the repository and install in editable mode for development:

```sh
git clone https://github.com/daan1392/andalus
cd andalus
pip install -e .
```

With `uv` (recommended — also installs dev dependencies from `pyproject.toml`):

```sh
git clone https://github.com/daan1392/andalus
cd andalus
uv sync
```

`uv sync` creates an isolated virtual environment under `.venv/`. Activate it before running commands:

```sh
# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

## Verifying the installation

```python
import andalus
print(andalus.__version__)
```

## Optional: NJOY / SANDY for ACE export

The `AssimilationSuite.to_ace()` method requires a working [NJOY](https://www.njoy21.io/) installation
accessible on your `PATH`, in addition to the `sandy` Python package.  This is only needed when you
want to export adjusted nuclear data to ACE format for use in a Monte Carlo transport code.
