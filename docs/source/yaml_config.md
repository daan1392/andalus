# YAML Configuration

`AssimilationSuite.from_yaml()` is the recommended entry point for production workflows.  A single
YAML file describes all benchmarks, applications, and the covariance library.

## Minimal example

```yaml
benchmarks:
  - title: HMI-001
    m: 1.0000
    dm: 0.0005
    sens0_path: data/hmi001_sens0.m
    results_path: data/hmi001_res.m

applications:
  - title: my-reactor
    sens0_path: data/reactor_sens0.m
    results_path: data/reactor_res.m

covariances:
  file_path: data/covariances.h5
```

Load with:

```python
from andalus import AssimilationSuite

suite = AssimilationSuite.from_yaml("assimilation.yaml")
posterior = suite.glls()
```

---

## `benchmarks` section

Each entry in the `benchmarks` list describes one integral experiment.  Two source formats are
supported: **Serpent files** and **HDF5**.

### From Serpent files

Required keys:

| Key | Type | Description |
| --- | --- | --- |
| `title` | string | Unique identifier |
| `m` | float | Measured value (e.g. $k_{\text{eff}}$) |
| `dm` | float | Measurement uncertainty ($1\sigma$) |
| `sens0_path` | string | Path to the Serpent `_sens0.m` file |
| `results_path` | string | Path to the Serpent `_res.m` file |

Optional keys:

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `kind` | string | `"keff"` | Observable type |
| `zailist` | list[int] | all | Subset of nuclides (ZAI numbers) to load |
| `pertlist` | list[int] | all | Subset of reactions (MT numbers) to load |
| `materials` | list | all | Subset of Serpent materials |
| `flux_det_name` | string | — | Detector name for the flux spectrum |
| `flux_det_path` | string | — | Path to the Serpent `_det0.m` file |

Example:

```yaml
benchmarks:
  - title: HMI-001
    m: 1.0000
    dm: 0.0005
    sens0_path: data/hmi001_sens0.m
    results_path: data/hmi001_res.m
    kind: keff
    zailist: [922350, 922380]
    pertlist: [18, 102]
    flux_det_name: FLUX
    flux_det_path: data/hmi001_det0.m
```

### From HDF5

Use `hdf5_path` instead of `sens0_path` / `results_path`.  You may load a single entry,
a named subset, or all entries from the file:

```yaml
benchmarks:
  # Single benchmark by title
  - title: HMI-001
    hdf5_path: data/benchmarks.h5

  # Named subset
  - titles: [HMI-001, HMI-002, HMI-003]
    hdf5_path: data/benchmarks.h5

  # All benchmarks in the file (omit titles / set to null)
  - hdf5_path: data/benchmarks.h5
```

Optional key:

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `kind` | string | `"keff"` | HDF5 group key |

---

## `applications` section

Identical structure to `benchmarks` except that `m` and `dm` are optional.

### From Serpent files

```yaml
applications:
  - title: my-reactor
    sens0_path: data/reactor_sens0.m
    results_path: data/reactor_res.m
    # Optional: provide a measurement if available
    m: 1.0023
    dm: 0.0010
```

### From HDF5

```yaml
applications:
  - title: my-reactor
    hdf5_path: data/applications.h5
```

---

## `covariances` section

The covariances section points to a single HDF5 file that contains pre-processed nuclear data
covariance matrices (produced via `Covariance.to_hdf5()`).

```yaml
covariances:
  file_path: data/covariances.h5
```

`AssimilationSuite.from_yaml()` automatically determines which nuclides (ZAIs) to load from the
union of all ZAIs present in the benchmark and application sensitivities.  The reactions loaded are
currently fixed to MT 2, 4, 18, 102, 456, and 35018.

---

## Full annotated example

```yaml
# benchmarks: integral experiments used to constrain nuclear data
benchmarks:
  # --- loaded from Serpent output ---
  - title: HMI-001
    m: 1.0000
    dm: 0.0005
    sens0_path: serpent/hmi001_sens0.m
    results_path: serpent/hmi001_res.m
    zailist: [922350, 922380, 942390]

  - title: PU-MET-FAST-001
    m: 1.0000
    dm: 0.0003
    sens0_path: serpent/pmf001_sens0.m
    results_path: serpent/pmf001_res.m
    flux_det_name: FLUX
    flux_det_path: serpent/pmf001_det0.m

  # --- loaded from HDF5 library ---
  - titles: [LEU-COMP-THERM-001, LEU-COMP-THERM-002]
    hdf5_path: db/icsbep_benchmarks.h5

# applications: systems to predict
applications:
  - title: reactor-core
    sens0_path: serpent/core_sens0.m
    results_path: serpent/core_res.m

  - title: waste-storage
    sens0_path: serpent/waste_sens0.m
    results_path: serpent/waste_res.m

# covariances: nuclear data covariance library
covariances:
  file_path: db/jeff40_covariances.h5
```
