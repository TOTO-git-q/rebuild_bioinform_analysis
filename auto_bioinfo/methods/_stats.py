"""Small, dependency-light statistics used by registered methods.

Only ``numpy`` is required at runtime.  The Student-t tail probability is
computed from the *regularised incomplete beta function* using the standard
continued-fraction algorithm (Numerical Recipes, ``betacf``/``betai``); this is
a well-established reference implementation, not an ad-hoc approximation, so the
two-sided p-values match ``scipy.stats.ttest_ind(..., equal_var=False)`` to ~1e-10
without taking scipy as a dependency.  Everything here is pure and deterministic.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    MAXIT = 200
    EPS = 3.0e-12
    FPMIN = 1.0e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < FPMIN:
        d = FPMIN
    d = 1.0 / d
    h = d
    for m in range(1, MAXIT + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < FPMIN:
            d = FPMIN
        c = 1.0 + aa / c
        if abs(c) < FPMIN:
            c = FPMIN
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < EPS:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """I_x(a, b), the regularised incomplete beta function, for 0 <= x <= 1."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_p(t: float, df: float) -> float:
    """Two-sided p-value for a Student-t statistic with ``df`` degrees of freedom."""
    if df <= 0 or not math.isfinite(t):
        return float("nan")
    x = df / (df + t * t)
    return regularized_incomplete_beta(df / 2.0, 0.5, x)


def welch_t_test(group_a: Sequence[float], group_b: Sequence[float]) -> dict[str, float]:
    """Welch's unequal-variance two-sample t-test.

    Returns t statistic, Welch-Satterthwaite degrees of freedom, two-sided
    p-value, the group means and the mean difference (a - b).
    """
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    na, nb = a.size, b.size
    if na < 2 or nb < 2:
        raise ValueError("welch_t_test requires at least 2 observations per group")
    ma, mb = float(a.mean()), float(b.mean())
    va, vb = float(a.var(ddof=1)), float(b.var(ddof=1))
    se2 = va / na + vb / nb
    if se2 == 0.0:
        # No variance: identical-within-group values.  Report a defined,
        # non-significant result rather than dividing by zero.
        return {"t": 0.0, "df": float(na + nb - 2), "p_value": 1.0, "mean_a": ma, "mean_b": mb, "mean_diff": ma - mb}
    t = (ma - mb) / math.sqrt(se2)
    df = se2 * se2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return {"t": t, "df": df, "p_value": student_t_two_sided_p(t, df), "mean_a": ma, "mean_b": mb, "mean_diff": ma - mb}


def benjamini_hochberg(p_values: Sequence[float]) -> list[float]:
    """Benjamini-Hochberg FDR adjustment; returns adjusted p-values in input order."""
    p = np.asarray(p_values, dtype=float)
    n = p.size
    if n == 0:
        return []
    order = np.argsort(p, kind="stable")
    ranked = p[order]
    ranks = np.arange(1, n + 1, dtype=float)
    adjusted = ranked * n / ranks
    # Enforce monotonicity from the largest p downward.
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    adjusted = np.clip(adjusted, 0.0, 1.0)
    out = np.empty(n, dtype=float)
    out[order] = adjusted
    return [float(v) for v in out]
