# History

## 0.1.2 (2026-03-05)

While v0.1.1 served as a workflow test, **v0.1.2** marks the first functional release of ANDALUS. This version establishes the core framework for data assimilation tasks and provides the necessary documentation to get started.

### 🌟 Key Highlights
* **Official Launch:** ANDALUS is now capable of performing fundamental data assimilation tasks using **least squares**.
* **YAML Configuration:** Added the ability to initialize an `AssimilationSuite` directly from a `.yaml` file for better workflow reproducibility.
* **Educational Resources:** Two example notebooks are now included, demonstrating how to interact with the `Sensitivity` and `AssimilationSuite` classes.
* **Improved Stability:** Significant increase in test coverage to ensure more robust performance.

### 🛠 Maintenance & Dependency Updates
* **GitHub Actions:** Updated `upload-artifact` (v7), `download-artifact` (v8), `attest-build-provenance` (v4), and `setup-uv` (v7.3.1).
* **Code Quality:** Addressed PR feedback and expanded the test suite for better edge-case handling.

### 🤝 New Contributors
* @Claude made their first contribution in https://github.com/daan1392/andalus/pull/5
* @dependabot[bot] made their first contribution in https://github.com/daan1392/andalus/pull/1

**Full Changelog**: https://github.com/daan1392/andalus/compare/v0.1.1...v0.1.2

---

## 0.1.1 (2026-02-25)

* First release on PyPI (Workflow & CI/CD test).