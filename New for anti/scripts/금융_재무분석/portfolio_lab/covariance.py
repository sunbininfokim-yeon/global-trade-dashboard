"""Covariance estimators: EWMA (short) and Ledoit–Wolf constant-correlation (long)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sample_cov(returns: pd.DataFrame) -> pd.DataFrame:
    return returns.cov()


def ewma_cov(returns: pd.DataFrame, lam: float = 0.94) -> pd.DataFrame:
    """RiskMetrics-style EWMA covariance on demeaned returns."""
    x = returns.values.astype(float)
    t, n = x.shape
    if t < 5:
        return returns.cov()
    mean = x.mean(axis=0)
    x = x - mean
    cov = np.cov(x, rowvar=False)
    for i in range(t):
        r = x[i : i + 1].T  # n x 1
        cov = lam * cov + (1.0 - lam) * (r @ r.T)
    return pd.DataFrame(cov, index=returns.columns, columns=returns.columns)


def ledoit_wolf_cov(returns: pd.DataFrame) -> pd.DataFrame:
    """
    Ledoit–Wolf shrinkage toward constant-correlation target (pure numpy).

    Reference: Ledoit & Wolf (2004), Honey, I Shrunk the Sample Covariance Matrix.
    """
    x = returns.values.astype(float)
    t, n = x.shape
    if n == 1:
        return returns.cov()
    x = x - x.mean(axis=0)
    sample = (x.T @ x) / t

    var = np.diag(sample).copy()
    std = np.sqrt(np.maximum(var, 1e-18))
    std_outer = np.outer(std, std)
    corr = sample / std_outer
    np.fill_diagonal(corr, 1.0)
    # mean correlation excluding diagonal
    mask = ~np.eye(n, dtype=bool)
    mean_corr = corr[mask].mean() if mask.any() else 0.0
    prior = mean_corr * std_outer
    np.fill_diagonal(prior, var)

    # shrinkage intensity (simplified LW formula)
    x2 = x ** 2
    phi_mat = (x2.T @ x2) / t - sample ** 2
    phi = float(phi_mat.sum())
    gamma = float(((sample - prior) ** 2).sum())
    kappa = phi / gamma if gamma > 1e-18 else 1.0
    shrink = max(0.0, min(1.0, kappa / t))
    sigma = shrink * prior + (1.0 - shrink) * sample
    # numerical hygiene
    eigvals, eigvecs = np.linalg.eigh(sigma)
    eigvals = np.maximum(eigvals, 1e-12)
    sigma = (eigvecs * eigvals) @ eigvecs.T
    # restore symmetry
    sigma = 0.5 * (sigma + sigma.T)
    out = pd.DataFrame(sigma, index=returns.columns, columns=returns.columns)
    out.attrs["shrinkage"] = shrink
    out.attrs["mean_corr"] = mean_corr
    return out


def corr_from_cov(cov: pd.DataFrame) -> pd.DataFrame:
    d = np.sqrt(np.maximum(np.diag(cov.values), 1e-18))
    corr = cov.values / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)
    return pd.DataFrame(corr, index=cov.index, columns=cov.columns)
