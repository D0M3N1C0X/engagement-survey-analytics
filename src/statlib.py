"""
Statistics for survey work - pure standard library.

Survey analysis needs a different toolkit from a headcount analysis: almost
everything is a proportion, groups are small enough that intervals matter, and
the drivers are heavily correlated with each other. So this module carries
Wilson intervals, two-proportion tests, and Johnson's relative weight analysis
on top of the usual regression machinery.
"""

from __future__ import annotations

import math


# --------------------------------------------------------------------------
# Descriptives
# --------------------------------------------------------------------------

def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def sd(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def quantile(xs: list[float], q: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def zscores(xs: list[float]) -> list[float]:
    m, s = mean(xs), sd(xs)
    return [0.0] * len(xs) if not s else [(x - m) / s for x in xs]


def pearson(xs: list[float], ys: list[float]) -> float:
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = math.sqrt(sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys))
    return num / den if den else float("nan")


def two_sided_p(z: float) -> float:
    return math.erfc(abs(z) / math.sqrt(2))


# --------------------------------------------------------------------------
# Proportions - the bread and butter of survey reporting
# --------------------------------------------------------------------------

def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """
    95% confidence interval for a proportion, Wilson score method.

    Preferred over the textbook normal interval because survey cuts are often
    small and the favourable rate is often near 0 or 1, exactly where the
    normal interval gives impossible bounds.
    """
    if n == 0:
        return (float("nan"), float("nan"))
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def two_proportion_z(k1: int, n1: int, k2: int, n2: int) -> tuple[float, float]:
    """Pooled two-proportion z-test: is this group really different, or is it noise?"""
    if min(n1, n2) == 0:
        return (float("nan"), float("nan"))
    p1, p2 = k1 / n1, k2 / n2
    pooled = (k1 + k2) / (n1 + n2)
    se = math.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (p1 - p2) / se
    return (z, two_sided_p(z))


# --------------------------------------------------------------------------
# Linear algebra
# --------------------------------------------------------------------------

def invert(matrix: list[list[float]]) -> list[list[float]]:
    """Gauss-Jordan inverse with partial pivoting."""
    n = len(matrix)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("singular matrix")
        a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        a[col] = [v / div for v in a[col]]
        for r in range(n):
            if r != col and a[r][col]:
                factor = a[r][col]
                a[r] = [v - factor * p for v, p in zip(a[r], a[col])]
    return [row[n:] for row in a]


def matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    cols = list(zip(*b))
    return [[sum(x * y for x, y in zip(row, col)) for col in cols] for row in a]


def jacobi_eigen(matrix: list[list[float]], sweeps: int = 100
                 ) -> tuple[list[float], list[list[float]]]:
    """
    Eigenvalues and eigenvectors of a symmetric matrix, cyclic Jacobi rotations.

    Returns (eigenvalues, eigenvectors as columns). Correlation matrices are
    small and well behaved, so the classic rotation method is plenty.
    """
    n = len(matrix)
    a = [row[:] for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]

    for _ in range(sweeps):
        off = math.sqrt(sum(a[i][j] ** 2 for i in range(n) for j in range(n) if i != j))
        if off < 1e-12:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-15:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = math.copysign(1.0, theta) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq

    return [a[i][i] for i in range(n)], v


# --------------------------------------------------------------------------
# Regression
# --------------------------------------------------------------------------

def ols_standardised(predictors: list[list[float]], outcome: list[float]) -> tuple[list[float], float]:
    """
    Standardised betas and R2. `predictors` is one list per variable.

    Both sides are z-scored, so the coefficients are directly comparable: a
    beta of 0.30 means one standard deviation on that driver moves engagement
    by 0.30 of a standard deviation.
    """
    X = [zscores(col) for col in predictors]
    y = zscores(outcome)
    k, n = len(X), len(y)

    xtx = [[sum(X[i][r] * X[j][r] for r in range(n)) for j in range(k)] for i in range(k)]
    xty = [sum(X[i][r] * y[r] for r in range(n)) for i in range(k)]
    inv = invert(xtx)
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]

    fitted = [sum(beta[i] * X[i][r] for i in range(k)) for r in range(n)]
    rss = sum((yr - f) ** 2 for yr, f in zip(y, fitted))
    tss = sum(yr * yr for yr in y)
    return beta, 1 - rss / tss


def relative_weights(predictors: list[list[float]], outcome: list[float]
                     ) -> tuple[list[float], float]:
    """
    Johnson's relative weight analysis.

    Survey drivers are correlated with each other - people who rate their
    manager well tend to rate recognition well - and raw regression
    coefficients handle that badly: they hand the shared variance to whichever
    driver happens to win the tie, and small sample changes reshuffle the
    ranking. Johnson's method builds an orthogonal counterpart of the
    predictor set, regresses on that, and transforms back, so each driver
    receives a share of the explained variance that reflects both its own
    relationship with the outcome and what it shares with the others.

    Returns (weights as a share of R2, R2). The weights sum to 1.
    """
    X = [zscores(col) for col in predictors]
    y = zscores(outcome)
    k, n = len(X), len(y)

    corr = [[pearson(X[i], X[j]) for j in range(k)] for i in range(k)]
    rxy = [pearson(X[i], y) for i in range(k)]

    values, vectors = jacobi_eigen(corr)
    values = [max(v, 1e-9) for v in values]

    # Delta = V * sqrt(Lambda) * V'  - the orthogonal approximation of X
    sqrt_lambda = [[math.sqrt(values[j]) if i == j else 0.0 for j in range(k)] for i in range(k)]
    delta = matmul(matmul(vectors, sqrt_lambda), list(map(list, zip(*vectors))))

    # beta on the orthogonal variables
    beta_star = [sum(invert(delta)[i][j] * rxy[j] for j in range(k)) for i in range(k)]

    raw = [sum((delta[i][j] ** 2) * (beta_star[j] ** 2) for j in range(k)) for i in range(k)]
    r2 = sum(raw)
    return ([w / r2 for w in raw] if r2 else [0.0] * k), r2
