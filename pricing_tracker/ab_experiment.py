"""Designed A/B experiment — pricing-page conversion test (SIMULATED data).

Scenario: a cloud provider tests whether adding a live per-GPU price-comparison
widget to its pricing page lifts trial sign-up conversion vs the static price
list. Real experiment data is proprietary, so the data here is simulated with
numpy — clearly labeled as such. What this module demonstrates is the design
discipline: hypothesis, minimum detectable effect, power analysis, sample-ratio
mismatch check, two-proportion z-test, confidence interval, and a ship decision.
"""
from __future__ import annotations

import math

import numpy as np

SEED = 20260611
BASELINE_CVR = 0.040     # control: static pricing page
TRUE_TREATMENT_CVR = 0.046  # simulated ground truth (+0.6pp)
MDE_PP = 0.005           # minimum detectable effect we care about: +0.5pp
ALPHA = 0.05
POWER = 0.80
DAILY_VISITORS = 1400


def z_quantile(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's approximation, no scipy needed)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        return -z_quantile(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def norm_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def required_n_per_arm(p1: float, mde: float, alpha: float, power: float) -> int:
    """Two-proportion sample size (normal approximation)."""
    p2 = p1 + mde
    p_bar = (p1 + p2) / 2
    z_a = z_quantile(1 - alpha / 2)
    z_b = z_quantile(power)
    num = (z_a * math.sqrt(2 * p_bar * (1 - p_bar))
           + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2
    return math.ceil(num / mde ** 2)


def run() -> dict:
    rng = np.random.default_rng(SEED)
    n_target = required_n_per_arm(BASELINE_CVR, MDE_PP, ALPHA, POWER)
    days_needed = math.ceil(2 * n_target / DAILY_VISITORS)

    # Simulate the experiment day by day (visitors split ~50/50).
    total = days_needed * DAILY_VISITORS
    assign = rng.random(total) < 0.5
    n_t, n_c = int(assign.sum()), int(total - assign.sum())
    conv_t = int(rng.binomial(n_t, TRUE_TREATMENT_CVR))
    conv_c = int(rng.binomial(n_c, BASELINE_CVR))

    # Sample-ratio mismatch check (chi-square, 1 df, expected 50/50).
    srm_chi2 = (n_t - total / 2) ** 2 / (total / 2) + (n_c - total / 2) ** 2 / (total / 2)
    srm_ok = srm_chi2 < 3.841  # chi2(1) at alpha=0.05

    p_t, p_c = conv_t / n_t, conv_c / n_c
    p_pool = (conv_t + conv_c) / (n_t + n_c)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n_t + 1 / n_c))
    z = (p_t - p_c) / se_pool
    p_value = 2 * (1 - norm_cdf(abs(z)))
    se_diff = math.sqrt(p_t * (1 - p_t) / n_t + p_c * (1 - p_c) / n_c)
    z975 = z_quantile(0.975)
    ci = ((p_t - p_c) - z975 * se_diff, (p_t - p_c) + z975 * se_diff)

    return {
        "n_target_per_arm": n_target, "days_needed": days_needed,
        "n_treatment": n_t, "n_control": n_c,
        "conv_treatment": conv_t, "conv_control": conv_c,
        "cvr_treatment": p_t, "cvr_control": p_c,
        "lift_pp": (p_t - p_c) * 100, "z": z, "p_value": p_value,
        "ci_pp": (ci[0] * 100, ci[1] * 100),
        "srm_chi2": srm_chi2, "srm_ok": srm_ok,
        "significant": p_value < ALPHA,
    }


if __name__ == "__main__":
    r = run()
    for k, v in r.items():
        print(f"{k}: {v}")
