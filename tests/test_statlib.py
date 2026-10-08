"""The statistics are written from scratch (no dependencies), so they are checked here against known
values and the properties that define them. Run with: python3 -m unittest discover -s tests"""
import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import statlib  # noqa: E402


class Proportions(unittest.TestCase):
    def test_wilson_reference_values(self):
        lo, hi = statlib.wilson_interval(50, 100)
        self.assertAlmostEqual(lo, 0.4038, places=4)
        self.assertAlmostEqual(hi, 0.5962, places=4)
        lo, hi = statlib.wilson_interval(0, 10)            # never below zero, unlike the normal interval
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=4)

    def test_two_proportion_z_matches_its_definition(self):
        z, p = statlib.two_proportion_z(60, 100, 45, 100)
        pooled = 105 / 200
        self.assertAlmostEqual(z, (0.60 - 0.45) / math.sqrt(pooled * (1 - pooled) * (2 / 100)))
        self.assertAlmostEqual(p, math.erfc(abs(z) / math.sqrt(2)))


class LinearAlgebra(unittest.TestCase):
    def test_jacobi_eigen_reconstructs_the_matrix(self):
        a = [[4.0, 1.0, 0.5], [1.0, 3.0, 0.2], [0.5, 0.2, 2.0]]
        values, vectors = statlib.jacobi_eigen(a)
        lam = [[values[i] if i == j else 0.0 for j in range(3)] for i in range(3)]
        back = statlib.matmul(statlib.matmul(vectors, lam), [list(r) for r in zip(*vectors)])
        for i in range(3):
            for j in range(3):
                self.assertAlmostEqual(back[i][j], a[i][j], places=9)


class RelativeWeights(unittest.TestCase):
    def setUp(self):
        rng = random.Random(3)
        n = 400
        manager = [rng.gauss(0, 1) for _ in range(n)]
        recognition = [0.7 * m + 0.7 * rng.gauss(0, 1) for m in manager]      # correlated drivers
        pay = [rng.gauss(0, 1) for _ in range(n)]
        self.X = [manager, recognition, pay]
        self.y = [0.6 * m + 0.3 * r + 0.1 * p + rng.gauss(0, 1) for m, r, p in zip(manager, recognition, pay)]

    def test_weights_sum_to_one_and_r2_is_the_regression_r2(self):
        w, r2 = statlib.relative_weights(self.X, self.y)
        _, r2_ols = statlib.ols_standardised(self.X, self.y)
        self.assertAlmostEqual(sum(w), 1.0, places=12)
        self.assertAlmostEqual(r2, r2_ols, places=9)
        self.assertEqual(max(range(3), key=lambda i: w[i]), 0)              # the strongest driver ranks first

    def test_orthogonal_drivers_get_their_squared_correlation(self):
        h1 = [1, 1, 1, 1, -1, -1, -1, -1]
        h2 = [1, 1, -1, -1, 1, 1, -1, -1]
        h3 = [1, -1, 1, -1, 1, -1, 1, -1]
        y = [2 * a + b + 0.5 * c + e for a, b, c, e in zip(h1, h2, h3, [0.3, -0.1, 0.2, 0.0, -0.4, 0.1, 0.05, -0.15])]
        w, r2 = statlib.relative_weights([h1, h2, h3], y)
        r = [statlib.pearson(h, y) for h in (h1, h2, h3)]
        for wi, ri in zip(w, r):
            self.assertAlmostEqual(wi * r2, ri ** 2, places=9)


if __name__ == "__main__":
    unittest.main()
