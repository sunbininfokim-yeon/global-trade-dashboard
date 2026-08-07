"""Allocation engines: Hierarchical Risk Parity (Lopez de Prado) + simple risk parity."""

from __future__ import annotations

import numpy as np
import pandas as pd


def _corr_distance(corr: np.ndarray) -> np.ndarray:
    c = np.clip(corr, -1.0, 1.0)
    return np.sqrt(0.5 * (1.0 - c))


def _hierarchical_clusters(dist: np.ndarray) -> list:
    """Average-linkage agglomerative clustering; returns list of (i,j,dist,size) merges + leaf order helpers."""
    n = dist.shape[0]
    # clusters map id -> list of leaf indices
    clusters: dict[int, list[int]] = {i: [i] for i in range(n)}
    active = set(range(n))
    dmat = dist.copy()
    next_id = n
    merges: list[tuple[int, int, int]] = []  # (id_a, id_b, new_id)

    while len(active) > 1:
        ids = sorted(active)
        best = None
        best_val = np.inf
        for ii, a in enumerate(ids):
            for b in ids[ii + 1 :]:
                # average linkage between members
                members_a, members_b = clusters[a], clusters[b]
                block = dist[np.ix_(members_a, members_b)]
                val = float(block.mean())
                if val < best_val:
                    best_val = val
                    best = (a, b)
        assert best is not None
        a, b = best
        clusters[next_id] = clusters[a] + clusters[b]
        merges.append((a, b, next_id))
        active.remove(a)
        active.remove(b)
        active.add(next_id)
        next_id += 1
    # leaf order = final cluster order
    root = next(iter(active))
    order = clusters[root]
    return order, merges, clusters


def _quasi_diag(corr: pd.DataFrame) -> list[int]:
    dist = _corr_distance(corr.values)
    order, _, _ = _hierarchical_clusters(dist)
    return order


def _cluster_var(cov: np.ndarray, items: list[int]) -> float:
    sub = cov[np.ix_(items, items)]
    # inverse-variance portfolio inside cluster
    iv = 1.0 / np.maximum(np.diag(sub), 1e-18)
    w = iv / iv.sum()
    return float(w @ sub @ w)


def hierarchical_risk_parity(cov: pd.DataFrame) -> pd.Series:
    """
    HRP weights (López de Prado). Long-only, sums to 1.
    """
    cols = list(cov.columns)
    n = len(cols)
    if n == 0:
        return pd.Series(dtype=float)
    if n == 1:
        return pd.Series({cols[0]: 1.0})

    corr = cov.copy()
    d = np.sqrt(np.maximum(np.diag(cov.values), 1e-18))
    corr_v = cov.values / np.outer(d, d)
    np.fill_diagonal(corr_v, 1.0)
    corr = pd.DataFrame(corr_v, index=cov.index, columns=cov.columns)

    order = _quasi_diag(corr)
    cov_v = cov.values
    w = np.ones(n)

    # recursive bisection on ordered list
    def bisect(items: list[int]) -> None:
        if len(items) <= 1:
            return
        split = len(items) // 2
        left, right = items[:split], items[split:]
        var_l = _cluster_var(cov_v, left)
        var_r = _cluster_var(cov_v, right)
        alpha = 1.0 - var_l / (var_l + var_r)
        for i in left:
            w[i] *= alpha
        for i in right:
            w[i] *= 1.0 - alpha
        bisect(left)
        bisect(right)

    bisect(order)
    # map back from position in order? w indexed by original indices 0..n-1
    # During bisect we used original leaf indices from `order` which are original ids — good.
    ser = pd.Series(w, index=cols, dtype=float)
    ser = ser / ser.sum()
    return ser


def risk_parity_weights(cov: pd.DataFrame, tol: float = 1e-8, max_iter: int = 500) -> pd.Series:
    """Simple iterative risk parity (equal risk contribution), long-only."""
    sigma = cov.values.astype(float)
    n = sigma.shape[0]
    w = np.ones(n) / n
    for _ in range(max_iter):
        port_var = float(w @ sigma @ w)
        if port_var <= 0:
            break
        mrc = sigma @ w
        rc = w * mrc
        target = port_var / n
        # update
        w_new = w * (target / np.maximum(rc, 1e-18))
        w_new = np.maximum(w_new, 0.0)
        w_new = w_new / w_new.sum()
        if np.linalg.norm(w_new - w) < tol:
            w = w_new
            break
        w = w_new
    return pd.Series(w, index=cov.index, dtype=float)


def apply_max_weight_caps(
    weights: pd.Series,
    caps: dict[str, float],
) -> pd.Series:
    """Iteratively cap weights and redistribute residual to uncapped names."""
    w = weights.astype(float).copy()
    if w.sum() <= 0:
        return w
    w = w / w.sum()
    for _ in range(20):
        over = {k: caps[k] for k in w.index if k in caps and w[k] > caps[k] + 1e-12}
        if not over:
            break
        free = 0.0
        for k, cap in over.items():
            free += w[k] - cap
            w[k] = cap
        others = [i for i in w.index if i not in over]
        if not others:
            break
        add = free * (w[others] / w[others].sum()) if w[others].sum() > 0 else free / len(others)
        w[others] = w[others] + add
    return w / w.sum()
