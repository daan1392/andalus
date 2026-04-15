# Quickstart

This guide walks through a complete nuclear data assimilation workflow from loading Serpent output
files to producing a posterior and exporting adjusted nuclear data.

## Overview

A typical ANDALUS workflow consists of four steps:

1. **Load benchmarks** — Serpent sensitivity and results files for experiments with known measurements.
2. **Load applications** — Serpent sensitivity and results files for the system you want to predict.
3. **Load covariances** — Nuclear data covariance matrices from ERRORR (via SANDY).
4. **Run GLLS** — Combine everything in an `AssimilationSuite` and call `.glls()`.

## Step 1: Load a benchmark

```python
from andalus import Benchmark

hmi = Benchmark.from_serpent(
    title="HMI-001",
    m=1.0,          # measured k-eff
    dm=0.0005,      # measurement uncertainty (1-sigma)
    sens0_path="data/hmi001_sens0.m",
    results_path="data/hmi001_res.m",
    kind="keff",
)

print(f"k_eff discrepancy: {hmi.c - hmi.m:.5f}")
```

To attach a flux spectrum (needed for the `ealf` metric), pass `flux_det`:

```python
hmi = Benchmark.from_serpent(
    title="HMI-001",
    m=1.0,
    dm=0.0005,
    sens0_path="data/hmi001_sens0.m",
    results_path="data/hmi001_res.m",
    flux_det=("FLUX", "data/hmi001_det0.m"),
)
```

## Step 2: Load a benchmark suite

```python
from andalus import BenchmarkSuite

suite = BenchmarkSuite.from_yaml("benchmarks.yaml")

# Or build from a list
suite = BenchmarkSuite.from_list([hmi, hmi2, hmi3])

print(suite.m)   # measured values as pd.Series
print(suite.c)   # calculated values as pd.Series
```

## Step 3: Load covariances

```python
from andalus import CovarianceSuite

covariances = CovarianceSuite.from_hdf5(
    "covariances.h5",
    zais=[922350, 922380, 942390],  # U-235, U-238, Pu-239
)
```

## Step 4: Load applications

```python
from andalus import Application, ApplicationSuite

reactor = Application.from_serpent(
    title="my-reactor",
    sens0_path="data/reactor_sens0.m",
    results_path="data/reactor_res.m",
)

applications = ApplicationSuite.from_list([reactor])
```

## Step 5: Run GLLS and inspect results

```python
from andalus import AssimilationSuite

suite = AssimilationSuite(
    benchmarks=benchmark_suite,
    applications=applications,
    covariances=covariances,
)

posterior = suite.glls()

posterior.summarize()
print(f"Chi-squared: {posterior.chi_squared():.3f}")
print(posterior.applications.c)   # adjusted calculated values
```

## Step 6: Export to ACE (optional)

If NJOY is installed and you want to use the adjusted nuclear data in a Monte Carlo transport code:

```python
posterior.to_ace(
    library="jeff_40",
    temperature=300,
    create_xsdata=True,
)
```

## Using a YAML configuration

For reproducible workflows, describe everything in a single YAML file and load it in one call:

```python
suite = AssimilationSuite.from_yaml("assimilation.yaml")
posterior = suite.glls()
```

See the [YAML Configuration](yaml_config.md) page for the full schema.

## Filtering benchmarks

Remove outliers before running GLLS using composable filter objects:

```python
from andalus import Chi2Filter

# Keep only benchmarks with chi-squared < 3
filtered = suite.filter(Chi2Filter(threshold=3.0))
posterior = filtered.glls()
```

Filters support `&`, `|`, and `~` operators:

```python
from andalus import Chi2Filter, Chi2NuclearDataFilter

f = Chi2Filter(3.0) & Chi2NuclearDataFilter(3.0, covariances.matrix)
posterior = suite.filter(f).glls()
```
