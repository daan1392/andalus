# User Guide

## Data model overview

ANDALUS is built around a small set of composable data classes that mirror the components of the
GLLS workflow.  Each item class has a corresponding suite class that aggregates multiple items and
exposes combined `pd.Series`/`pd.DataFrame` properties.

| Item class | Suite class | Holds |
| --- | --- | --- |
| `Benchmark` | `BenchmarkSuite` | Experiment with measurement $m$, uncertainty $\sigma_m$, calculated value $c$, and sensitivity $S$ |
| `Application` | `ApplicationSuite` | System of interest — same shape as `Benchmark` but $m$ is optional |
| `Covariance` | `CovarianceSuite` | Nuclear data covariance for one or more nuclides |
| — | `AssimilationSuite` | Orchestrator that holds all three suites and runs GLLS |

---

## Sensitivity

`Sensitivity` is a `pd.DataFrame` subclass with a four-level MultiIndex `(ZAI, MT, E_min_eV, E_max_eV)`
and two columns: the sensitivity values and their standard deviations.

### Loading from Serpent

```python
from andalus import Sensitivity

s = Sensitivity.from_serpent(
    sens0_path="data/hmi001_sens0.m",
    title="HMI-001",
    kind="keff",
    zailist=[922350, 922380],   # optional subset of nuclides
    pertlist=[18, 102],         # optional subset of reactions (MT numbers)
)
```

### Plotting

```python
ax = s.plot_sensitivity(
    zais=[922350],
    perts=["total fission", "capture"],
)
```

### Persistence

```python
s.to_hdf5("sensitivities.h5")
s2 = Sensitivity.from_hdf5("sensitivities.h5", title="HMI-001")
```

---

## Benchmark

`Benchmark` is a frozen dataclass.  Once created it cannot be modified; use the suite-level
`update_c()` method when you need to propagate new calculated values.

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `title` | `str` | Unique name |
| `kind` | `str` | Observable type (e.g. `"keff"`) |
| `m` | `float` | Measured value |
| `dm` | `float` | Measurement uncertainty ($1\sigma$) |
| `c` | `float` | Calculated value |
| `dc` | `float` | Calculation uncertainty ($1\sigma$) |
| `s` | `Sensitivity` | Energy-group sensitivity profiles |
| `flux` | `FluxSpectrum \| None` | Flux spectrum (optional) |

### Loading from Serpent

```python
from andalus import Benchmark

b = Benchmark.from_serpent(
    title="HMI-001",
    m=1.0000,
    dm=0.0005,
    sens0_path="data/hmi001_sens0.m",
    results_path="data/hmi001_res.m",
)
```

Attach a flux spectrum by passing `flux_det=(detector_name, det_path)`:

```python
b = Benchmark.from_serpent(
    title="HMI-001",
    m=1.0000,
    dm=0.0005,
    sens0_path="data/hmi001_sens0.m",
    results_path="data/hmi001_res.m",
    flux_det=("FLUX", "data/hmi001_det0.m"),
)
```

### Persistence

```python
b.to_hdf5("benchmarks.h5")
b2 = Benchmark.from_hdf5("benchmarks.h5", title="HMI-001")
```

---

## Application

`Application` has the same shape as `Benchmark` but `m` and `dm` are optional.  Use it for any
nuclear system whose response you want to predict (but may not have a measurement for).

```python
from andalus import Application

app = Application.from_serpent(
    title="my-reactor",
    sens0_path="data/reactor_sens0.m",
    results_path="data/reactor_res.m",
    # m and dm are optional
)
```

---

## Covariance

`Covariance` is a `pd.DataFrame` subclass that holds the multigroup cross-section covariance matrix
for a single nuclide (ZAI).  The index is a MultiIndex `(MF, MT, E_min_eV, E_max_eV)`.

### Loading from ERRORR files

NJOY ERRORR output files are read via [SANDY](https://sandy-code.readthedocs.io/):

```python
from andalus import Covariance

cov = Covariance.from_errorr(
    files={"tape33": "data/u235.errorr"},
    zai=922350,
    mts=[18, 102],     # fission and capture
)
```

### Persistence

```python
cov.to_hdf5("covariances.h5")
cov2 = Covariance.from_hdf5("covariances.h5", zai=922350)
```

### Diagnostics

```python
print(cov.correlation())           # correlation matrix
print(cov.is_unrealistic_uncertainty(threshold=10))  # True if any σ > 1000 %
```

---

## CovarianceSuite

`CovarianceSuite` wraps a block-diagonal covariance matrix that spans multiple nuclides and
reactions.  Its `.matrix` attribute is the global `pd.DataFrame` with a five-level MultiIndex
`(ZAI, MF, MT, E_min_eV, E_max_eV)`.

```python
from andalus import CovarianceSuite

# Load from HDF5 (most common)
cov_suite = CovarianceSuite.from_hdf5(
    "covariances.h5",
    zais=[922350, 922380, 942390],
    mts=[2, 18, 102],
)

# Build from individual Covariance objects
from andalus import Covariance
cov_suite = CovarianceSuite.from_dict({
    922350: cov_u235,
    922380: cov_u238,
})

# Inspect uncertainties
print(cov_suite.get_uncertainties())

# Visualise uncertainty for U-235 capture (MT=102)
cov_suite.plot_uncertainty(zai=922350, mt=102)
```

---

## AssimilationSuite

`AssimilationSuite` is the top-level orchestrator.  It holds a `BenchmarkSuite`, an
`ApplicationSuite`, and a `CovarianceSuite`, and exposes the full GLLS workflow.

### Construction

```python
from andalus import AssimilationSuite

suite = AssimilationSuite(
    benchmarks=benchmark_suite,
    applications=application_suite,
    covariances=covariance_suite,
)
```

The recommended approach for reproducible workflows is to use `from_yaml()`:

```python
suite = AssimilationSuite.from_yaml("assimilation.yaml")
```

### Aggregated properties

All suite classes expose combined properties as `pd.Series` or `pd.DataFrame`:

```python
suite.m     # measured values (benchmarks only)
suite.dm    # measurement uncertainties
suite.c     # calculated values (benchmarks + applications)
suite.dc    # calculation uncertainties
suite.s     # sensitivity matrix (rows = cases, cols = nuclear data)
```

### Running GLLS

```python
posterior = suite.glls()
```

Pass `include_sensitivity_uncertainty=True` to account for the statistical uncertainty on the
sensitivity profiles themselves:

```python
posterior = suite.glls(include_sensitivity_uncertainty=True)
```

### Inspecting the posterior

```python
posterior.summarize()

# Per-benchmark chi-squared
print(posterior.individual_chi_squared())

# Total chi-squared (with and without nuclear data term)
print(posterior.chi_squared(nuclear_data=False))
print(posterior.chi_squared(nuclear_data=True))

# Adjusted calculated values for applications
print(posterior.applications.c)

# Nuclear data adjustment vector
print(posterior.xs_adjustment)
```

### Similarity analysis

The $c_k$ matrix quantifies how similar two cases are in terms of their nuclear data sensitivity:

```python
ck = suite.ck_matrix()   # square DataFrame, rows and cols = all case titles
print(ck)

# Similarity of all cases with a specific application
print(suite.ck_target("my-reactor"))
```

### Uncertainty propagation

Propagate the prior nuclear data uncertainty to the calculated response vector:

```python
uncertainty = suite.propagate_nuclear_data_uncertainty()
print(uncertainty)   # pd.Series, one value per case
```

### Exporting to ACE

After running GLLS, export the adjusted nuclear data to ACE format for use in Serpent or other
Monte Carlo codes (requires NJOY on `PATH`):

```python
posterior.to_ace(
    library="jeff_40",
    temperature=300,
    create_xsdata=True,
    parallel=True,
)
```

Use `only_zais_applications=True` to limit the export to nuclides that actually appear in the
application sensitivities.

---

## Filtering benchmarks

The `filter()` method on suites accepts any callable `Benchmark → bool`, including the built-in
filter objects.

### Built-in filters

| Filter | Description |
| --- | --- |
| `Chi2Filter(threshold)` | Keeps benchmarks where $\chi^2 \le$ threshold |
| `Chi2NuclearDataFilter(threshold, cov_matrix)` | Keeps benchmarks where the nuclear-data-inclusive $\chi^2 \le$ threshold |

### Composing filters

Filter objects support boolean operators:

```python
from andalus import Chi2Filter, Chi2NuclearDataFilter

f_exp   = Chi2Filter(3.0)
f_ndata = Chi2NuclearDataFilter(3.0, suite.covariances.matrix)

# Both conditions must hold
filtered = suite.filter(f_exp & f_ndata)

# At least one condition must hold
filtered = suite.filter(f_exp | f_ndata)

# Negate a filter
filtered = suite.filter(~f_exp)
```

### Custom filters

Any callable that accepts a `Benchmark` and returns a `bool` works:

```python
# Keep only fast-spectrum benchmarks
fast_only = lambda b: b.flux is not None and b.flux.ealf > 1e4  # EALF > 10 keV
filtered = suite.filter(fast_only)
```

---

## HDF5 storage

ANDALUS uses `pandas` HDF5 tables as its on-disk format, making it easy to accumulate large
libraries of benchmarks and covariances across sessions.

```python
# Save
benchmark.to_hdf5("benchmarks.h5")
application.to_hdf5("applications.h5")
covariance.to_hdf5("covariances.h5")

# Load individual items
b = Benchmark.from_hdf5("benchmarks.h5", title="HMI-001")
a = Application.from_hdf5("applications.h5", title="my-reactor")
c = Covariance.from_hdf5("covariances.h5", zai=922350)

# Load entire suites
bs = BenchmarkSuite.from_hdf5("benchmarks.h5", titles=None)          # all
bs = BenchmarkSuite.from_hdf5("benchmarks.h5", titles=["HMI-001"])   # subset
```

The HDF5 layout is:

```
{kind}/
  {title}/
    sensitivity    ← pandas table (Sensitivity)
    flux           ← pandas table (FluxSpectrum, optional)
    attrs: m, dm, c, dc
```

---

## Utility functions

### `sandwich`

The core $\mathbf{s}_1^\top \mathbf{C} \, \mathbf{s}_2$ operation used throughout uncertainty
propagation:

```python
from andalus import sandwich

# Propagate covariance through two sensitivity vectors
result = sandwich(s1, cov_matrix, s2)

# Auto-transpose: s2 defaults to s1 when omitted
variance = sandwich(s, cov_matrix)
```

### `sandwich_binwise` / `uncertainty_reactionwise`

Decompose the total uncertainty into contributions per energy bin or per reaction (ZAI/MT pair):

```python
from andalus.utils import sandwich_binwise, uncertainty_reactionwise

bin_contributions  = sandwich_binwise(s, cov)
rxn_contributions  = uncertainty_reactionwise(s, cov)
```
