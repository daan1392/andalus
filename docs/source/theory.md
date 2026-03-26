# Theory

## Introduction

The accurate simulation of nuclear systems—ranging from commercial power reactors to advanced next-generation designs and criticality safety applications—relies heavily on the underlying fundamental nuclear data. These data include neutron-induced cross-sections, angular distributions, fission yields, and decay constants. However, despite decades of dedicated measurement campaigns and theoretical evaluations, nuclear data is inherently uncertain. When these fundamental parameters are used in neutron transport codes to simulate complex systems, the underlying uncertainties propagate through the calculations, leading to uncertainties in integral macroscopic parameters such as the effective neutron multiplication factor ($k_{\text{eff}}$), reaction rates, and reactivity coefficients.

To improve the predictive capabilities of computational models for future applications, it is essential to learn from past experiments. Historically, numerous integral benchmark experiments have been conducted worldwide, and many have been rigorously evaluated and cataloged (e.g., in the International Handbook of Evaluated Criticality Safety Benchmark Experiments). These integral benchmarks provide macroscopic observations of how a nuclear system behaves in reality. By comparing the calculated results against these experimental observations, discrepancies often arise. These discrepancies represent a wealth of information. Through the process of nuclear data assimilation—specifically using the generalized least squares approach—we can consolidate this integral information with our prior differential nuclear data to produce an adjusted, physically consistent nuclear data vector that systematically reduces calculation biases and uncertainties.

## Nuclear Data and Uncertainties

Fundamental nuclear data parameters are derived from a combination of differential measurements (such as time-of-flight cross-section measurements at linear accelerators) and theoretical nuclear reaction models (like Hauser-Feshbach statistical models or optical models). Due to experimental measurement limits, resolution broadening, background subtractions, and approximations in theoretical models, the evaluated nuclear data contains inherent uncertainties.

More importantly, these uncertainties are rarely independent. Correlated systematic errors in experimental setups (e.g., a shared flux monitor standard) and the constraints imposed by nuclear reaction theory (where different reaction channels must sum to the total cross-section) introduce significant correlations between different energy groups, different reaction types, and even different isotopes. 

Mathematically, these uncertainties and their correlations are described by nuclear data covariance matrices. Let $\boldsymbol{\alpha}$ represent the vector of fundamental nuclear data parameters (e.g., multigroup cross-sections). The covariance matrix of these parameters, typically denoted as $\mathbf{M}_{\boldsymbol{\alpha}}$, is an $N \times N$ symmetric, positive semi-definite matrix, where $N$ is the number of nuclear data parameters. The diagonal elements of $\mathbf{M}_{\boldsymbol{\alpha}}$ represent the variances (squared standard deviations) of the individual parameters, while the off-diagonal elements quantify the covariance (or correlation) between different parameters. A robust description of how nuclear data behaves and how its uncertainties are structured is foundational to any data assimilation methodology.

## Sensitivity Analysis

To utilize the integral benchmark data for adjusting the fundamental nuclear data $\boldsymbol{\alpha}$, we must understand exactly how a variation in a specific nuclear data parameter impacts the calculated integral response. Let $R(\boldsymbol{\alpha})$ be a calculated integral response (e.g., $k_{\text{eff}}$) which depends on the nuclear data vector $\boldsymbol{\alpha}$.

Because the nuclear data variations within their physical uncertainty bounds are typically small relative to the absolute magnitude of the cross-sections, we can approximate the change in the integral response using a first-order Taylor series expansion. This is valid as long as the uncertainties remain small, ensuring that the system's response to perturbations is predominantly linear.

The absolute sensitivity coefficient is defined as the partial derivative of the response with respect to the nuclear data parameter. In practice, it is often more convenient to use relative sensitivity coefficients, defined as the fractional change in the response resulting from a fractional change in the nuclear data parameter:

$$
S_{i} = \frac{\alpha_i}{R} \frac{\partial R}{\partial \alpha_i}
$$

For a system with multiple responses and multiple parameters, we construct a sensitivity matrix $\mathbf{S}$. If there are $I$ integral responses and $N$ nuclear data parameters, $\mathbf{S}$ is an $I \times N$ matrix where each element $S_{i,j}$ describes the relative sensitivity of the $i$-th integral response to the $j$-th nuclear data parameter. These sensitivity coefficients are typically computed using first-order generalized perturbation theory (GPT) within the neutron transport codes, requiring the solution of both the forward and the adjoint fluxes. 

By employing this linear approximation, the expected change in the calculated response vector $\Delta \mathbf{R}$ due to a change in the nuclear data vector $\Delta \boldsymbol{\alpha}$ is simply given by the matrix-vector multiplication:

$$
\Delta \mathbf{R} = \mathbf{S} \Delta \boldsymbol{\alpha}
$$

## Generalized Least Squares (GLS) Adjustment

The goal of Applied Nuclear Data Assimilation Using Least sqUareS (ANDALUS) is to find a new, optimal nuclear data vector $\boldsymbol{\alpha}'$ that best fits both the prior differential nuclear data knowledge and the available integral benchmark experiments. This is achieved by minimizing a loss function (or cost function) $\chi^2$, which quantifies the discrepancy between the adjusted data and the prior data, as well as the discrepancy between the calculated responses and the experimental measurements, weighted by their respective inverse covariance matrices.

Let:
- $\boldsymbol{\alpha}_0$ be the a priori nuclear data vector.
- $\mathbf{M}_{\boldsymbol{\alpha}}$ be the prior covariance matrix of the nuclear data.
- $\mathbf{R}_e$ be the vector of experimental integral measurements.
- $\mathbf{M}_e$ be the covariance matrix of the experimental uncertainties (including experimental correlations).
- $\mathbf{R}_c(\boldsymbol{\alpha})$ be the vector of computed integral responses using data $\boldsymbol{\alpha}$.
- $\mathbf{M}_c$ be the covariance matrix representing computational method uncertainties (often combined with $\mathbf{M}_e$).

The generalized least squares method seeks the adjusted parameter vector $\boldsymbol{\alpha}'$ completely defined by minimizing the following quadratic form:

$$
\chi^2 = (\boldsymbol{\alpha}' - \boldsymbol{\alpha}_0)^T \mathbf{M}_{\boldsymbol{\alpha}}^{-1} (\boldsymbol{\alpha}' - \boldsymbol{\alpha}_0) + (\mathbf{R}_e - \mathbf{R}_c(\boldsymbol{\alpha}'))^T \mathbf{M}_e^{-1} (\mathbf{R}_e - \mathbf{R}_c(\boldsymbol{\alpha}'))
$$

Using the first-order approximation $\mathbf{R}_c(\boldsymbol{\alpha}') \approx \mathbf{R}_c(\boldsymbol{\alpha}_0) + \mathbf{S} (\boldsymbol{\alpha}' - \boldsymbol{\alpha}_0)$, and minimizing the $\chi^2$ function with respect to $\boldsymbol{\alpha}'$ by setting its derivative to zero, yields the standard analytical solution for the adjusted nuclear data vector:

$$
\boldsymbol{\alpha}' = \boldsymbol{\alpha}_0 + \mathbf{M}_{\boldsymbol{\alpha}} \mathbf{S}^T \left( \mathbf{S} \mathbf{M}_{\boldsymbol{\alpha}} \mathbf{S}^T + \mathbf{M}_e \right)^{-1} (\mathbf{R}_e - \mathbf{R}_c(\boldsymbol{\alpha}_0))
$$

Furthermore, the adjustment process also updates the covariance matrix of the nuclear data, reflecting the information gained from the integral experiments. The a posteriori covariance matrix $\mathbf{M}_{\boldsymbol{\alpha}}'$ is given by:

$$
\mathbf{M}_{\boldsymbol{\alpha}}' = \mathbf{M}_{\boldsymbol{\alpha}} - \mathbf{M}_{\boldsymbol{\alpha}} \mathbf{S}^T \left( \mathbf{S} \mathbf{M}_{\boldsymbol{\alpha}} \mathbf{S}^T + \mathbf{M}_e \right)^{-1} \mathbf{S} \mathbf{M}_{\boldsymbol{\alpha}}
$$

This equation explicitly shows that the a posteriori uncertainties ($\mathbf{M}_{\boldsymbol{\alpha}}'$) are strictly smaller than or equal to the a priori uncertainties ($\mathbf{M}_{\boldsymbol{\alpha}}$), demonstrating that applying the least squares technique with benchmark data effectively reduces the overall uncertainty in our fundamental data libraries and, subsequently, in future predictive modeling.