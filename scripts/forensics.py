#!/usr/bin/env python3
"""
Academic Data Forensics Toolkit
================================
Statistical methods for detecting potential data fabrication in published research.

Methods:
  1. Benford's Law        — First-digit distribution test
  2. GRIM test             — Granularity-Related Inconsistency of Means
  3. p-curve analysis      — p-hacking detection via p-value distribution
  4. Bootstrap audit       — Resampled consistency check
  5. Sample-size sanity    — SD/CI vs N impossibility check
  6. Mass balance          — Input-output consistency (environmental)
  7. Formula audit         — Missing conversion factor detection
  8. Monte Carlo sniff     — Parameter distribution plausibility
  9. Summary stats check   — Mean/SD/N internal consistency
 10. Digit preference      — Terminal digit rounding anomalies

Usage:
  python forensics.py audit --paper paper_data.json
  python forensics.py benford 12.5,34.2,67.8,...
  python forensics.py grim --mean 3.47 --n 30 --dp 2
  python forensics.py report --input audit_results.json
"""

import math
import json
import sys
import argparse

# Import pysprite for advanced SPRITE/GRIM (vendored from QuentinAndre/pysprite, MIT)
try:
    from pysprite_vendor import grim as pysprite_grim, Sprite as Pysprite
    HAS_PYSPRITE = True
except ImportError:
    HAS_PYSPRITE = False

from collections import Counter
from typing import List, Dict, Tuple, Optional

# ============================================================
# 1. BENFORD'S LAW
# ============================================================

# Expected proportions for digits 1-9
BENFORD_EXPECTED = {
    1: 0.301, 2: 0.176, 3: 0.125, 4: 0.097,
    5: 0.079, 6: 0.067, 7: 0.058, 8: 0.051, 9: 0.046
}

def benford_test(values: List[float], method: str = "both") -> dict:
    """
    Test if first digits follow Benford's Law.
    
    Args:
        values: List of positive numbers
        method: "chi2", "mad", or "both"
    
    Returns:
        dict with test results and interpretation
    
    Interpretation:
        MAD < 0.006: Close conformity
        MAD 0.006-0.012: Acceptable conformity  
        MAD 0.012-0.015: Marginally acceptable
        MAD > 0.015: Non-conformity (RED FLAG)
        
        chi2 p < 0.05: Significant deviation from Benford
    """
    # Extract first digits
    first_digits = []
    for v in values:
        if v <= 0:
            continue
        # Get first significant digit
        s = f"{v:.10f}".lstrip('0').replace('.', '')
        if s:
            first_digits.append(int(s[0]))
    
    n = len(first_digits)
    if n < 10:
        return {"error": "Need at least 10 positive values", "n": n}
    
    counts = Counter(first_digits)
    
    # Chi-square test
    chi2 = 0
    for d in range(1, 10):
        observed = counts.get(d, 0)
        expected = BENFORD_EXPECTED[d] * n
        chi2 += (observed - expected) ** 2 / expected
    
    # MAD (Mean Absolute Deviation)
    mad = 0
    for d in range(1, 10):
        observed_p = counts.get(d, 0) / n
        mad += abs(observed_p - BENFORD_EXPECTED[d])
    mad /= 9
    
    # Interpretation
    if mad < 0.006:
        mad_level = "CLOSE CONFORMITY"
        mad_flag = "green"
    elif mad < 0.012:
        mad_level = "ACCEPTABLE"
        mad_flag = "green"
    elif mad < 0.015:
        mad_level = "MARGINALLY ACCEPTABLE"
        mad_flag = "yellow"
    else:
        mad_level = "NON-CONFORMITY — POTENTIAL MANIPULATION"
        mad_flag = "red"
    
    # Chi-square critical values (df=8): 15.51 for p=0.05, 20.09 for p=0.01
    chi2_flag = "red" if chi2 > 15.51 else ("yellow" if chi2 > 12.0 else "green")
    
    detail = {}
    for d in range(1, 10):
        detail[d] = {
            "observed": counts.get(d, 0),
            "expected": round(BENFORD_EXPECTED[d] * n, 1),
            "observed_pct": round(counts.get(d, 0) / n * 100, 1),
            "expected_pct": round(BENFORD_EXPECTED[d] * 100, 1)
        }
    
    return {
        "method": "Benford's Law (First Digit)",
        "n": n,
        "chi2": round(chi2, 2),
        "chi2_flag": chi2_flag,
        "chi2_critical_05": 15.51,
        "mad": round(mad, 4),
        "mad_level": mad_level,
        "mad_flag": mad_flag,
        "detail": detail,
        "verdict": "PASS" if mad_flag == "green" and chi2_flag == "green" else \
                   "WARNING" if mad_flag == "yellow" or chi2_flag == "yellow" else "RED FLAG"
    }


# ============================================================
# 2. GRIM TEST (Granularity-Related Inconsistency of Means)
# ============================================================

def grim_test(reported_mean: float, n: int, decimal_places: int = 2,
              variable_name: str = "variable") -> dict:
    """
    Test if a reported mean is mathematically possible given integer data and sample size.
    
    Theory: For integer-valued data reported to D decimal places with N participants,
    the mean × N must be an integer (to within rounding).
    
    Args:
        reported_mean: The mean value reported in the paper
        n: Sample size
        decimal_places: Number of decimal places the mean is reported to
        variable_name: Name of the variable for reporting
    
    Returns:
        dict with test result
    """
    granularity = 10 ** (-decimal_places)
    product = reported_mean * n
    
    # Check if product is an integer (within rounding tolerance)
    rounded = round(product)  # nearest integer
    diff = abs(product - rounded)
    
    # If the difference is > granularity_window, it's impossible
    # Typical tolerance: 0.01 for 2dp means
    tolerance = granularity * max(n, 1) * 0.55  # generous tolerance
    
    if diff <= tolerance:
        is_consistent = True
        # Find possible integer values
        possible_ints = []
        for offset in range(-2, 3):
            candidate = rounded + offset
            if candidate >= 0:
                recalc_mean = candidate / n
                if abs(round(recalc_mean, decimal_places) - reported_mean) < granularity:
                    possible_ints.append(candidate)
        
        return {
            "method": "GRIM Test",
            "variable": variable_name,
            "reported_mean": reported_mean,
            "n": n,
            "decimal_places": decimal_places,
            "mean_times_n": product,
            "nearest_integer": rounded,
            "difference": round(diff, 4),
            "is_consistent": True,
            "verdict": "PASS — Mean is mathematically possible",
            "possible_total_counts": possible_ints[:5]  # top 5
        }
    else:
        return {
            "method": "GRIM Test",
            "variable": variable_name,
            "reported_mean": reported_mean,
            "n": n,
            "decimal_places": decimal_places,
            "mean_times_n": product,
            "nearest_integer": rounded,
            "difference": round(diff, 4),
            "is_consistent": False,
            "verdict": "RED FLAG — Reported mean is mathematically IMPOSSIBLE for integer data with N={}".format(n),
            "message": f"Mean × N = {product:.4f} is not an integer. The reported mean cannot arise from integer-valued data with N={n}."
        }


# ============================================================
# 3. P-CURVE ANALYSIS
# ============================================================

def pcurve_test(p_values: List[float], test_type: str = "two-tailed") -> dict:
    """
    Test for p-hacking by examining the distribution of significant p-values.
    
    Theory: If there's a true effect, p-values should be right-skewed (more p < 0.01 than p ~ 0.04).
    If p-hacked, p-values cluster just below 0.05.
    
    Args:
        p_values: List of p-values (should all be < 0.05 ideally)
        test_type: "one-tailed" or "two-tailed"
    
    Returns:
        dict with p-curve metrics
    """
    if not p_values:
        return {"error": "No p-values provided"}
    
    # Filter to significant values
    sig = [p for p in p_values if p < 0.05]
    if len(sig) < 4:
        return {"error": "Need at least 4 significant p-values for p-curve", "n_sig": len(sig)}
    
    # Bin into ranges
    bins = {"p<0.01": 0, "0.01-0.02": 0, "0.02-0.03": 0, "0.03-0.04": 0, "0.04-0.05": 0}
    for p in sig:
        if p < 0.01:
            bins["p<0.01"] += 1
        elif p < 0.02:
            bins["0.01-0.02"] += 1
        elif p < 0.03:
            bins["0.02-0.03"] += 1
        elif p < 0.04:
            bins["0.03-0.04"] += 1
        else:
            bins["0.04-0.05"] += 1
    
    # Binomial test: is the proportion of p<0.025 higher than 0.5?
    # Under null of uniform distribution, expect 50% below 0.025
    below_025 = sum(1 for p in sig if p < 0.025)
    total_sig = len(sig)
    expected_half = total_sig / 2
    
    # Right-skew test: more in p<0.01 than p 0.04-0.05?
    skew_ratio = bins["p<0.01"] / max(bins["0.04-0.05"], 1)
    
    # Clumping test: unusually many in 0.04-0.05?
    clump_pct = bins["0.04-0.05"] / total_sig * 100
    
    # Interpretation
    if skew_ratio >= 2.0:
        skew_verdict = "Evidential value (right-skewed, true effect likely)"
        skew_flag = "green"
    elif skew_ratio >= 1.0:
        skew_verdict = "Inconclusive (flat p-curve)"
        skew_flag = "yellow"
    else:
        skew_verdict = "P-hacking suspected (left-skewed, p-values clumped near 0.05)"
        skew_flag = "red"
    
    if clump_pct > 40:
        clump_verdict = "RED FLAG: >40% of p-values in 0.04-0.05 bin"
    elif clump_pct > 30:
        clump_verdict = "WARNING: Elevated p-value clustering near 0.05"
    else:
        clump_verdict = "Normal p-value distribution"
    
    return {
        "method": "p-curve Analysis",
        "n_total": len(p_values),
        "n_significant": total_sig,
        "bins": bins,
        "skew_ratio": round(skew_ratio, 2),
        "skew_verdict": skew_verdict,
        "skew_flag": skew_flag,
        "clump_pct_04_05": round(clump_pct, 1),
        "clump_verdict": clump_verdict,
        "verdict": "RED FLAG" if skew_flag == "red" else \
                   "WARNING" if skew_flag == "yellow" or clump_pct > 30 else "PASS"
    }


# ============================================================
# 4. SAMPLE-SIZE SANITY
# ============================================================

def sample_size_sanity(mean: float, sd: float, n: int, ci: Optional[float] = None,
                       ci_level: float = 0.95, variable_name: str = "variable") -> dict:
    """
    Check if reported SD/CI is compatible with reported sample size.
    
    Theory: SD = SEM * sqrt(N), so SEM can be derived from CI width.
    If the reported SD would require negative values or impossible ranges, flag it.
    """
    sem = sd / math.sqrt(n)
    
    # Z for CI level
    z_map = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}
    z = z_map.get(ci_level, 1.96)
    
    ci_half = z * sem
    
    issues = []
    
    # Check 1: Does CI cross zero when it shouldn't?
    if ci is not None:
        # Compare reported CI to computed CI
        computed_ci_width = 2 * ci_half
        # If reported CI is much narrower than expected, flag
        pass
    
    # Check 2: Could SD be too large relative to mean? (CV check)
    cv = sd / abs(mean) if mean != 0 else float('inf')
    if cv > 2.0:
        issues.append(f"Coefficient of variation = {cv:.1f} (>2.0, extremely high variability)")
    elif cv > 1.0:
        issues.append(f"Coefficient of variation = {cv:.1f} (>1.0, high variability)")
    
    # Check 3: Does mean - 2*SD go below physically possible minimum?
    lower_bound = mean - 2 * sd
    if lower_bound < 0:
        issues.append(f"Mean - 2*SD = {lower_bound:.2f} (negative — impossible for non-negative data?)")
    
    # Check 4: Is N unusually round? (multiples of 10 are common in fabricated data)
    n_roundness = "exact multiple of 10" if n % 10 == 0 else \
                  "exact multiple of 5" if n % 5 == 0 else "not notably round"
    
    return {
        "method": "Sample-Size Sanity Check",
        "variable": variable_name,
        "mean": mean,
        "sd": sd,
        "n": n,
        "sem": round(sem, 4),
        "ci_half_width_95": round(1.96 * sem, 4),
        "cv": round(cv, 2),
        "lower_2sd": round(lower_bound, 2),
        "n_roundness": n_roundness,
        "issues": issues,
        "verdict": "RED FLAG" if len(issues) >= 3 else \
                   "WARNING" if issues else "PASS"
    }


# ============================================================
# 5. BOOTSTRAP AUDIT
# ============================================================

def bootstrap_audit(reported_stats: dict, n_iter: int = 1000, seed: int = 42) -> dict:
    """
    Check if reported statistics are plausible by parametric bootstrap.
    
    Given: mean, sd, n (and optionally min, max)
    Generates N_iter samples from Normal(mean, sd) truncated to [min, max]
    and checks if the reported statistics fall within the bootstrap distribution.
    
    Args:
        reported_stats: dict with keys 'mean', 'sd', 'n', and optionally 'min', 'max'
        n_iter: Number of bootstrap iterations
        seed: Random seed for reproducibility
    
    Returns:
        dict with bootstrap comparison
    """
    import random
    random.seed(seed)
    
    mean = reported_stats['mean']
    sd = reported_stats['sd']
    n = reported_stats['n']
    lo = reported_stats.get('min', -float('inf'))
    hi = reported_stats.get('max', float('inf'))
    
    bootstrap_means = []
    bootstrap_sds = []
    
    for _ in range(n_iter):
        sample = []
        for _ in range(n):
            # Truncated normal
            while True:
                x = random.gauss(mean, sd)
                if lo <= x <= hi:
                    sample.append(x)
                    break
        m = sum(sample) / n
        s = math.sqrt(sum((x - m) ** 2 for x in sample) / (n - 1))
        bootstrap_means.append(m)
        bootstrap_sds.append(s)
    
    bootstrap_means.sort()
    bootstrap_sds.sort()
    
    mean_ci_lo = bootstrap_means[int(n_iter * 0.025)]
    mean_ci_hi = bootstrap_means[int(n_iter * 0.975)]
    sd_ci_lo = bootstrap_sds[int(n_iter * 0.025)]
    sd_ci_hi = bootstrap_sds[int(n_iter * 0.975)]
    
    mean_in_ci = mean_ci_lo <= mean <= mean_ci_hi
    sd_in_ci = sd_ci_lo <= sd <= sd_ci_hi
    
    flags = []
    if not mean_in_ci:
        flags.append("Reported mean outside bootstrap 95% CI")
    if not sd_in_ci:
        flags.append("Reported SD outside bootstrap 95% CI")
    
    return {
        "method": "Bootstrap Audit (Parametric)",
        "n_iterations": n_iter,
        "mean_95ci": [round(mean_ci_lo, 4), round(mean_ci_hi, 4)],
        "sd_95ci": [round(sd_ci_lo, 4), round(sd_ci_hi, 4)],
        "mean_in_ci": mean_in_ci,
        "sd_in_ci": sd_in_ci,
        "flags": flags,
        "verdict": "PASS" if not flags else "WARNING"
    }


# ============================================================
# 6. MASS BALANCE CHECK
# ============================================================

def mass_balance_check(inputs: dict, outputs: dict, accumulation: float = 0,
                        tolerance: float = 0.05, system_name: str = "system") -> dict:
    """
    Environmental science: check if inputs = outputs + accumulation.
    
    Args:
        inputs: dict of {stream_name: value}
        outputs: dict of {stream_name: value}
        accumulation: net accumulation in system
        tolerance: Relative tolerance (0.05 = 5%)
        system_name: Name for reporting
    
    Returns:
        dict with balance check results
    """
    total_in = sum(inputs.values())
    total_out = sum(outputs.values())
    
    expected_out = total_in - accumulation
    imbalance = total_out - expected_out
    rel_imbalance = abs(imbalance) / max(total_in, 0.001)
    
    is_balanced = rel_imbalance <= tolerance
    
    return {
        "method": "Mass Balance Check",
        "system": system_name,
        "total_input": round(total_in, 4),
        "total_output": round(total_out, 4),
        "accumulation": accumulation,
        "expected_output": round(expected_out, 4),
        "imbalance": round(imbalance, 4),
        "relative_imbalance_pct": round(rel_imbalance * 100, 2),
        "tolerance_pct": round(tolerance * 100, 1),
        "is_balanced": is_balanced,
        "verdict": "PASS" if is_balanced else \
                   f"WARNING: {rel_imbalance*100:.1f}% imbalance exceeds {tolerance*100:.0f}% tolerance"
    }


# ============================================================
# 7. Result FORMULA AUDIT
# ============================================================

def formula_audit(reported_value: float, ds: float, factor_a: float = 0.65,
                       factor_b: float = 0.55, factor_c: float = 0.35) -> dict:
    """
    Check if reported Result production is consistent with the correct formula.
    
    Correct:   Result = DS * 1000 * factor_conversion * eta_AD * k_Result
                          = Intermediate * eta_AD * k_Result
    Wrong:     Result = DS * 1000 * eta_AD * k_Result  (missing factor_conversion, inflates by 1/factor_conversion)
    
    Args:
        reported_value: Reported Result value (Nm3/yr or similar)
        ds: Dry solids (t/yr or kg/d)
        factor_a: Intermediate/DS ratio (default 0.65)
        factor_b: Anaerobic degradation rate (default 0.55)
        factor_c: Result yield coefficient (Nm3/kgVS, default 0.35)
    
    Returns:
        dict with formula audit results
    """
    # Correct formula
    result_correct = ds * 1000 * factor_a * factor_b * factor_c
    
    # Wrong formula (missing factor_conversion)
    result_wrong = ds * 1000 * factor_b * factor_c
    
    # Which formula matches reported?
    ratio_correct = reported_value / result_correct if result_correct > 0 else float('inf')
    ratio_wrong = reported_value / result_wrong if result_wrong > 0 else float('inf')
    
    # Check closeness
    close_to_correct = abs(ratio_correct - 1.0) < 0.10
    close_to_wrong = abs(ratio_wrong - 1.0) < 0.10
    
    if close_to_correct:
        formula_used = "CORRECT (includes Intermediate/DS factor)"
        flag = "green"
    elif close_to_wrong:
        formula_used = "WRONG — Missing Intermediate/DS factor (factor_conversion=0.65), inflates Result by 1.54x"
        flag = "red"
    else:
        formula_used = f"UNCLEAR — Matches neither correct ({result_correct:.1f}) nor wrong ({result_wrong:.1f}) formula"
        flag = "yellow"
    
    return {
        "method": "Formula Audit",
        "reported_value": reported_value,
        "ds": ds,
        "factor_a": factor_a,
        "factor_b": factor_b,
        "factor_c": factor_c,
        "result_correct_formula": round(result_correct, 2),
        "result_wrong_formula": round(result_wrong, 2),
        "ratio_to_correct": round(ratio_correct, 3),
        "ratio_to_wrong": round(ratio_wrong, 3),
        "formula_used": formula_used,
        "flag": flag,
        "verdict": "PASS" if flag == "green" else "RED FLAG" if flag == "red" else "WARNING"
    }


# ============================================================
# 8. MONTE CARLO PARAMETER SNIFF
# ============================================================

def mc_parameter_sniff(parameters: List[dict]) -> dict:
    """
    Check if Monte Carlo parameter distributions are physically plausible.
    
    Common red flags:
    - Normal distribution for bounded parameters (e.g., rate 0-1)
    - Distribution mean far from literature consensus
    - Unusually narrow SD relative to literature range
    
    Args:
        parameters: List of dicts, each with:
            name, dist_type (normal/uniform/triangular/bootstrap),
            params (dist parameters), physical_range [min, max] (optional),
            literature_range [min, max] (optional)
    
    Returns:
        dict with parameter audit results
    """
    issues = []
    
    for p in parameters:
        name = p['name']
        dist_type = p['dist_type'].lower()
        prange = p.get('physical_range')
        lit_range = p.get('literature_range')
        
        # Check 1: Normal for bounded [0,1] parameter
        if dist_type == 'normal' and prange:
            lo, hi = prange
            if lo == 0 and hi == 1:
                # Normal on [0,1] is almost always wrong
                mean_val = p['params'][0]
                sd_val = p['params'][1] if len(p['params']) > 1 else 0
                # What fraction falls outside [0,1]?
                if sd_val > 0:
                    p_below = 0.5 * (1 + math.erf((0 - mean_val) / (sd_val * math.sqrt(2))))
                    p_above = 0.5 * (1 + math.erf((mean_val - 1) / (sd_val * math.sqrt(2))))
                    out_of_bounds = (p_below + p_above) * 100
                    if out_of_bounds > 5:
                        issues.append(
                            f"'{name}': Normal distribution on [0,1] with {out_of_bounds:.0f}% "
                            f"probability mass outside bounds. Use Triangular or Beta instead."
                        )
        
        # Check 2: Distribution doesn't cover literature range
        if dist_type == 'uniform' and lit_range:
            u_lo, u_hi = p['params'][0], p['params'][1]
            lit_lo, lit_hi = lit_range
            if u_lo > lit_lo or u_hi < lit_hi:
                issues.append(
                    f"'{name}': Uniform({u_lo},{u_hi}) doesn't fully cover "
                    f"literature range [{lit_lo}, {lit_hi}]"
                )
        
        # Check 3: Triangular mode suspiciously central
        if dist_type == 'triangular':
            lo, mode, hi = p['params'][0], p['params'][1], p['params'][2]
            centrality = (mode - lo) / (hi - lo) if hi > lo else 0.5
            if 0.48 < centrality < 0.52:
                issues.append(
                    f"'{name}': Triangular mode at exact center ({centrality:.2f}). "
                    f"Most physical degradation parameters are skewed (expect mode > 0.5)."
                )
    
    return {
        "method": "Monte Carlo Parameter Sniff",
        "n_parameters": len(parameters),
        "issues": issues,
        "verdict": "PASS" if not issues else \
                   "RED FLAG" if len(issues) >= 3 else "WARNING"
    }


# ============================================================
# 9. DIGIT PREFERENCE (Terminal Digit Analysis)
# ============================================================

def digit_preference(values: List[float], decimal_places: int = 1) -> dict:
    """
    Check for abnormal rounding or digit preference patterns.
    
    Humans fabricating data tend to prefer certain terminal digits (0, 5)
    and avoid others (1, 9).
    
    Args:
        values: List of numeric values
        decimal_places: Which decimal place to analyze (1 = first decimal)
    
    Returns:
        dict with digit distribution analysis
    """
    factor = 10 ** decimal_places
    terminal_digits = []
    
    for v in values:
        # Extract the digit at specified decimal place
        scaled = abs(v) * factor
        digit = int(scaled) % 10
        terminal_digits.append(digit)
    
    n = len(terminal_digits)
    counts = Counter(terminal_digits)
    
    # Expected: uniform distribution (10% each)
    expected = n / 10
    chi2 = 0
    for d in range(10):
        observed = counts.get(d, 0)
        chi2 += (observed - expected) ** 2 / expected
    
    # Check specific biases
    zero_pct = counts.get(0, 0) / n * 100
    five_pct = counts.get(5, 0) / n * 100
    zero_five_pct = (counts.get(0, 0) + counts.get(5, 0)) / n * 100
    
    flags = []
    if zero_five_pct > 30:
        flags.append(f"Digits 0+5 account for {zero_five_pct:.0f}% (>30%, possible fabrication)")
    if chi2 > 16.92:  # chi2 critical for df=9, p=0.05
        flags.append(f"Digit distribution deviates from uniform (chi2={chi2:.1f}, p<0.05)")
    
    return {
        "method": "Digit Preference (Terminal Digit Analysis)",
        "decimal_place": decimal_places,
        "n": n,
        "chi2": round(chi2, 2),
        "zero_pct": round(zero_pct, 1),
        "five_pct": round(five_pct, 1),
        "zero_five_combined_pct": round(zero_five_pct, 1),
        "expected_each_pct": 10.0,
        "flags": flags,
        "verdict": "RED FLAG" if flags else "PASS"
    }


# ============================================================
# 10. SUMMARY STATS CONSISTENCY
# ============================================================

def summary_stats_consistency(groups: List[dict]) -> dict:
    """
    Check if summary statistics across multiple groups are internally consistent.
    
    Common red flags:
    - All SDs are suspiciously similar despite different means
    - Sample sizes are suspiciously round (all multiples of 10 or 20)
    - SEM * sqrt(N) gives different SDs for groups that should have similar variance
    
    Args:
        groups: List of dicts, each with 'mean', 'sd', 'n', 'label'
    
    Returns:
        dict with consistency analysis
    """
    if len(groups) < 2:
        return {"error": "Need at least 2 groups"}
    
    issues = []
    
    # Check 1: SD homogeneity (are all SDs suspiciously similar?)
    sds = [g['sd'] for g in groups]
    sd_cv = 0
    if sds:
        sd_mean = sum(sds) / len(sds)
        sd_sd = math.sqrt(sum((s - sd_mean) ** 2 for s in sds) / len(sds)) if len(sds) > 1 else 0
        sd_cv = sd_sd / sd_mean if sd_mean > 0 else 0
        if sd_cv < 0.05:
            issues.append(f"SDs nearly identical across groups (CV={sd_cv:.3f}). Suspicious uniformity.")
    
    # Check 2: Round N pattern
    ns = [g['n'] for g in groups]
    round_count = sum(1 for n in ns if n % 10 == 0)
    if round_count >= len(ns) * 0.75:
        issues.append(f"{round_count}/{len(ns)} sample sizes are multiples of 10. Possible fabrication.")
    
    # Check 3: Mean progression plausibility
    means = [g['mean'] for g in groups]
    diffs = [means[i+1] - means[i] for i in range(len(means)-1)] if len(means) > 1 else []
    equal_spacing = len(set(round(d, 2) for d in diffs)) == 1 if diffs else False
    if equal_spacing and len(diffs) >= 2:
        issues.append("Means are equally spaced — possible formula-generated data")
    
    return {
        "method": "Summary Statistics Consistency",
        "n_groups": len(groups),
        "sd_cv": round(sd_cv, 4),
        "round_n_ratio": f"{round_count}/{len(ns)}",
        "equal_spacing": equal_spacing,
        "issues": issues,
        "verdict": "RED FLAG" if len(issues) >= 2 else \
                   "WARNING" if issues else "PASS"
    }

# ============================================================
# 10A. SPRITE (Sample Parameter Reconstruction via Iterative TEchniques)
# ============================================================

def sprite_test(mean: float, sd: float, n: int, m_prec: int = 2, sd_prec: int = 2,
                min_val: float = 1, max_val: float = 7, scale_label: str = "1-7",
                n_dists: int = 5, max_iter: int = 10000) -> dict:
    """
    SPRITE: Attempt to reconstruct possible raw data distributions from reported
    summary statistics. If no valid distribution can be found, the reported
    statistics are likely fabricated.
    
    Based on Heathers et al. (2018). Re-implemented via QuentinAndre/pysprite.
    
    Args:
        mean: Reported mean
        sd: Reported standard deviation
        n: Sample size
        m_prec: Decimal precision of the mean
        sd_prec: Decimal precision of the SD
        min_val: Minimum possible value on the scale
        max_val: Maximum possible value on the scale
        scale_label: Label for the scale (e.g., "1-7 Likert")
        n_dists: Number of candidate distributions to search for
        max_iter: Max iterations per distribution search
    
    Returns:
        dict with SPRITE results
    """
    if not HAS_PYSPRITE:
        return {"error": "pysprite not available (requires numpy)", "method": "SPRITE", "verdict": "SKIPPED — pysprite requires numpy"}
    
    try:
        s = Pysprite(n, mean, sd, m_prec, sd_prec, min_val, max_val)
        result = s.find_possible_distributions(n_dists=n_dists, max_iter=max_iter)
        outcome, dists, k = result
        
        found = (outcome == 'Success' and k > 0)
        
        return {
            "method": "SPRITE (Sample Parameter Reconstruction)",
            "scale": scale_label,
            "reported_mean": mean,
            "reported_sd": sd,
            "n": n,
            "range": [min_val, max_val],
            "distributions_found": k,
            "sought": n_dists,
            "is_reconstructable": found,
            "outcome": outcome,
            "verdict": "PASS — Valid distributions found" if found else
                       "RED FLAG — No valid distribution can produce these summary statistics",
            "message": f"Found {k}/{n_dists} valid distributions" if found else
                       "The reported mean, SD, N, and scale range are mutually impossible."
        }
    except Exception as e:
        # Initialization fails if GRIM test fails or mean outside range
        err_msg = str(e)
        if "mean is not possible" in err_msg.lower() or "grim" in err_msg.lower():
            return {
                "method": "SPRITE",
                "scale": scale_label,
                "reported_mean": mean,
                "reported_sd": sd,
                "n": n,
                "range": [min_val, max_val],
                "is_reconstructable": False,
                "outcome": "GRIM Failure",
                "verdict": "RED FLAG — Mean is mathematically impossible (GRIM pre-check failed)",
                "message": err_msg
            }
        return {
            "method": "SPRITE",
            "scale": scale_label,
            "reported_mean": mean,
            "reported_sd": sd,
            "n": n,
            "range": [min_val, max_val],
            "is_reconstructable": False,
            "outcome": f"Error: {err_msg}",
            "verdict": "WARNING — SPRITE initialization failed"
        }

# Also expose enhanced GRIM via pysprite
def grim_test_enhanced(mean: float, n: int, decimal_places: int = 2,
                        n_items: int = 1, variable_name: str = "variable") -> dict:
    """
    Enhanced GRIM test using pysprite's implementation (more robust).
    Falls back to our native implementation if pysprite not available.
    """
    if HAS_PYSPRITE:
        valid = pysprite_grim(n, mean, prec=decimal_places, n_items=n_items)
        product = round(mean * n * n_items, 4)
        nearest = round(product)
        return {
            "method": "GRIM Test (pysprite)",
            "variable": variable_name,
            "reported_mean": mean,
            "n": n,
            "n_items": n_items,
            "decimal_places": decimal_places,
            "mean_times_n_items": product,
            "nearest_integer": nearest,
            "is_consistent": valid,
            "verdict": "PASS — Mean is mathematically possible" if valid else
                       "RED FLAG — Reported mean is mathematically IMPOSSIBLE"
        }
    else:
        return grim_test(reported_mean=mean, n=n, decimal_places=decimal_places,
                         variable_name=variable_name)

# ============================================================
# 11. STATCHECK — Recompute p-values from test statistics
# ============================================================

def statcheck(test_statistic: float, df1: int, df2: Optional[int] = None,
              test_type: str = "t", reported_p: Optional[float] = None,
              tails: int = 2) -> dict:
    """
    Verify if a reported p-value matches the reported test statistic and df.
    This is the core functionality of statcheck (Nuijten et al., 2016).
    
    Supports: t-test, F-test, chi-square, Z-test
    
    Args:
        test_statistic: The reported test statistic value (t, F, chi2, or Z)
        df1: Degrees of freedom (numerator df for F-test)
        df2: Denominator df (for F-test only)
        test_type: "t", "F", "chi2", or "z"
        reported_p: The reported p-value (if available)
        tails: 1 or 2 for one-tailed or two-tailed test
    
    Returns:
        dict with recomputed p-value and consistency check
    """
    import math
    
    # Recompute p-value from test statistic
    if test_type == "t":
        # t-distribution survival function
        # Using approximation: t -> z for large df, or exact computation
        p_recomputed = _t_sf(abs(test_statistic), df1) * tails
        p_recomputed = min(p_recomputed, 1.0)
        
    elif test_type == "F":
        if df2 is None:
            return {"error": "F-test requires df2 (denominator df)"}
        p_recomputed = _f_sf(test_statistic, df1, df2)
        
    elif test_type == "chi2":
        p_recomputed = _chi2_sf(test_statistic, df1)
        
    elif test_type == "z":
        # Normal distribution
        p_recomputed = _z_sf(abs(test_statistic)) * tails
        p_recomputed = min(p_recomputed, 1.0)
        
    else:
        return {"error": f"Unknown test type: {test_type}"}
    
    # Determine significance at common thresholds
    sig_001 = p_recomputed < 0.001
    sig_01 = p_recomputed < 0.01
    sig_05 = p_recomputed < 0.05
    
    # Categorize p-value
    if p_recomputed < 0.001:
        p_category = "p < .001"
    elif p_recomputed < 0.01:
        p_category = "p < .01"
    elif p_recomputed < 0.05:
        p_category = "p < .05"
    else:
        p_category = "ns"
    
    result = {
        "method": "Statcheck (p-value Verification)",
        "test_type": test_type,
        "reported_statistic": test_statistic,
        "df": [df1, df2] if df2 is not None else [df1],
        "recomputed_p": round(p_recomputed, 6),
        "p_category": p_category,
        "tails": tails
    }
    
    if reported_p is not None:
        # Compare reported vs recomputed
        # Statcheck's criterion: inconsistency if the recomputed p is 
        # statistically significant at a different level than reported
        reported_sig_05 = reported_p < 0.05
        recomputed_sig_05 = p_recomputed < 0.05
        
        # Gross error: one is significant, the other is not
        gross_error = reported_sig_05 != recomputed_sig_05
        
        # Also check if the p-values are in the same ballpark (<.01 vs <.001, etc.)
        reported_sig_01 = reported_p < 0.01
        recomputed_sig_01 = p_recomputed < 0.01
        
        level_mismatch = (reported_sig_05 != recomputed_sig_05) or                          (reported_sig_01 != recomputed_sig_01 and reported_sig_05 == recomputed_sig_05)
        
        result["reported_p"] = reported_p
        result["gross_error"] = gross_error
        result["level_mismatch"] = level_mismatch
        
        if gross_error:
            result["verdict"] = "RED FLAG — Reported p-value contradicts test statistic"
            result["message"] = (
                f"Reported p={reported_p} ({'significant' if reported_sig_05 else 'ns'}), "
                f"but recomputed p={p_recomputed:.6f} ({'significant' if recomputed_sig_05 else 'ns'}). "
                f"The test statistic {test_type}({df1}{', '+str(df2) if df2 else ''})={test_statistic} "
                f"yields a different significance conclusion."
            )
        elif level_mismatch:
            result["verdict"] = "WARNING — p-value significance level mismatch"
            result["message"] = (
                f"Reported p={reported_p}, recomputed p={p_recomputed:.6f}. "
                f"Both agree on significance but disagree on level."
            )
        else:
            result["verdict"] = "PASS — Reported p-value consistent with test statistic"
    else:
        result["verdict"] = "INFO — p-value recomputed (no reported p to compare)"
    
    return result


def batch_statcheck(results_list: List[dict]) -> dict:
    """
    Run statcheck on multiple reported results.
    
    Args:
        results_list: List of dicts, each with:
            test_statistic, df1, df2 (optional), test_type, reported_p (optional)
    
    Returns:
        Summary dict with counts of errors
    """
    individual = []
    gross_errors = 0
    warnings = 0
    total = 0
    
    for r in results_list:
        result = statcheck(
            r['test_statistic'], r['df1'],
            r.get('df2'), r.get('test_type', 't'),
            r.get('reported_p'), r.get('tails', 2)
        )
        individual.append(result)
        total += 1
        if 'RED FLAG' in result.get('verdict', ''):
            gross_errors += 1
        elif 'WARNING' in result.get('verdict', ''):
            warnings += 1
    
    error_rate = gross_errors / total * 100 if total > 0 else 0
    
    return {
        "method": "Batch Statcheck",
        "total_tests": total,
        "gross_errors": gross_errors,
        "warnings": warnings,
        "error_rate_pct": round(error_rate, 1),
        "individual_results": individual,
        "verdict": "RED FLAG" if error_rate > 20 else                    "WARNING" if error_rate > 5 else                    "PASS" if total > 0 else "NO DATA",
        "message": (
            f"{gross_errors}/{total} tests ({error_rate:.0f}%) have p-values "
            f"inconsistent with their test statistics. "
            f"In psychology, ~12.5% of papers contain at least one such error (Nuijten 2016)."
        )
    }


# ---- Internal helper: statistical distribution functions ----

def _t_sf(t: float, df: int) -> float:
    """Survival function for t-distribution (Welch-Satterthwaite approximation)."""
    import math
    if df <= 0:
        return 0.5  # degenerate
    # Use Abramowitz & Stegun approximation
    x = df / (df + t * t)
    # Incomplete beta function approximation via regularized incomplete beta
    return _betai(0.5 * df, 0.5, x) / 2 if t >= 0 else 1 - _betai(0.5 * df, 0.5, x) / 2

def _f_sf(f: float, df1: int, df2: int) -> float:
    """Survival function for F-distribution."""
    if f <= 0:
        return 1.0
    x = df2 / (df2 + df1 * f)
    return _betai(0.5 * df2, 0.5 * df1, x)

def _chi2_sf(chi2: float, df: int) -> float:
    """Survival function for chi-square distribution."""
    if chi2 <= 0:
        return 1.0
    return _gammainc_q(0.5 * df, 0.5 * chi2)

def _z_sf(z: float) -> float:
    """Survival function for standard normal (1 - Phi(z))."""
    import math
    # Abramowitz & Stegun 26.2.17
    p = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    t = 1.0 / (1.0 + p * z)
    phi = 1.0 - (1.0 / math.sqrt(2 * math.pi)) * math.exp(-z*z/2) *           (b1*t + b2*t**2 + b3*t**3 + b4*t**4 + b5*t**5)
    return 1.0 - phi

def _betai(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function (continued fraction method)."""
    import math
    if x < 0.0 or x > 1.0:
        return 0.0
    if x == 0.0 or x == 1.0:
        return x
    
    # Compute log of beta function
    bt = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) +          a * math.log(x) + b * math.log(1.0 - x)
    
    if x < (a + 1.0) / (a + b + 2.0):
        # Use continued fraction directly
        return math.exp(bt) * _betacf(a, b, x) / a
    else:
        # Use symmetry relation
        return 1.0 - math.exp(bt) * _betacf(b, a, 1.0 - x) / b

def _betacf(a: float, b: float, x: float, max_iter: int = 100) -> float:
    """Continued fraction for incomplete beta."""
    import math
    eps = 1e-15
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_ = d * c
        h *= del_
        
        if abs(del_ - 1.0) < eps:
            break
    
    return h

def _gammainc_q(a: float, x: float) -> float:
    """Regularized upper incomplete gamma function Q(a,x)."""
    import math
    if x < 0 or a <= 0:
        return 0.0
    if x < a + 1.0:
        # Series expansion
        return 1.0 - _gser(a, x)
    else:
        # Continued fraction
        return _gcf(a, x)

def _gser(a: float, x: float, max_iter: int = 200) -> float:
    """Series expansion for incomplete gamma P(a,x)."""
    import math
    eps = 1e-15
    gln = math.lgamma(a)
    ap = a
    sum_ = 1.0 / a
    del_ = sum_
    for n in range(1, max_iter + 1):
        ap += 1.0
        del_ *= x / ap
        sum_ += del_
        if abs(del_) < abs(sum_) * eps:
            break
    return sum_ * math.exp(-x + a * math.log(x) - gln)

def _gcf(a: float, x: float, max_iter: int = 200) -> float:
    """Continued fraction for incomplete gamma Q(a,x)."""
    import math
    eps = 1e-15
    gln = math.lgamma(a)
    b = x + 1.0 - a
    c = 1.0 / 1e-30
    d = 1.0 / b
    h = d
    for i in range(1, max_iter + 1):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        if abs(d) < 1e-30:
            d = 1e-30
        c = b + an / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        del_ = d * c
        h *= del_
        if abs(del_ - 1.0) < eps:
            break
    return math.exp(-x + a * math.log(x) - gln) * h


# ============================================================
# 12. EFFECT SIZE CONSISTENCY CHECK
# ============================================================

def effect_size_consistency(mean1: float, mean2: float, sd_pooled: float,
                             reported_d: float, tol: float = 0.05) -> dict:
    """
    Check if reported Cohen's d is consistent with reported means and SD.
    
    Cohen's d = (M1 - M2) / SD_pooled
    
    Args:
        mean1, mean2: Group means
        sd_pooled: Pooled (or control group) standard deviation
        reported_d: The paper's reported Cohen's d
        tol: Relative tolerance
    
    Returns:
        dict with consistency check
    """
    if sd_pooled == 0:
        return {"error": "SD_pooled is zero"}
    
    computed_d = abs(mean1 - mean2) / sd_pooled
    rel_diff = abs(computed_d - reported_d) / max(abs(reported_d), 0.001)
    
    is_consistent = rel_diff < tol
    
    return {
        "method": "Effect Size Consistency (Cohen's d)",
        "mean_difference": round(abs(mean1 - mean2), 4),
        "sd_pooled": sd_pooled,
        "computed_d": round(computed_d, 4),
        "reported_d": round(reported_d, 4),
        "relative_difference_pct": round(rel_diff * 100, 1),
        "is_consistent": is_consistent,
        "verdict": "PASS" if is_consistent else
                   f"RED FLAG — Computed d={computed_d:.3f} vs reported d={reported_d:.3f} ({rel_diff*100:.0f}% difference)"
    }

# ============================================================
# 13. SCALE BOUNDARY CHECK (Psychology, Social Sciences, Medicine)
# ============================================================

def scale_boundary_check(mean: float, sd: float, min_val: float, max_val: float,
                          n: int = 30, label: str = "scale") -> dict:
    """
    Check if reported mean/SD are possible given the scale's physical boundaries.
    
    Common in Likert scales, clinical scales, and any bounded measurement.
    Red flags: mean outside [min, max], SD impossibly large for bounded scale.
    
    Args:
        mean: Reported mean
        sd: Reported SD
        min_val: Minimum possible value on the scale
        max_val: Maximum possible value on the scale
        n: Sample size (for variance bound calculation)
        label: Scale name for reporting
    """
    issues = []
    
    # Check 1: Mean within bounds
    if mean < min_val:
        issues.append(f"Mean ({mean}) is BELOW the scale minimum ({min_val}) — physically impossible")
    elif mean > max_val:
        issues.append(f"Mean ({mean}) is ABOVE the scale maximum ({max_val}) — physically impossible")
    
    # Check 2: Variance bound (max variance for bounded scale)
    # For a variable bounded in [a, b], max variance is (b-a)^2/4
    max_var = (max_val - min_val) ** 2 / 4
    reported_var = sd ** 2
    
    if reported_var > max_var * 1.01:  # 1% tolerance
        issues.append(
            f"SD ({sd}) is impossibly large: max possible SD for [{min_val},{max_val}] "
            f"is {math.sqrt(max_var):.2f} (variance bound = (b-a)^2/4 = {max_var:.2f})"
        )
    
    # Check 3: If mean is exactly at boundary, variance should be near zero
    if abs(mean - min_val) < 0.01 or abs(mean - max_val) < 0.01:
        if sd > (max_val - min_val) * 0.3:
            issues.append(
                f"Mean at scale boundary ({mean}) but SD is large ({sd}). "
                f"If all responses are at the boundary, SD should be ~0."
            )
    
    range_span = max_val - min_val
    cv = sd / max(abs(mean), 0.001) if mean != 0 else float('inf')
    
    return {
        "method": "Scale Boundary Check",
        "scale": label,
        "range": [min_val, max_val],
        "reported_mean": mean,
        "reported_sd": sd,
        "cv": round(cv, 2),
        "max_possible_sd": round(math.sqrt(max_var), 2),
        "issues": issues,
        "verdict": "RED FLAG" if len(issues) >= 2 else \
                   "WARNING" if issues else "PASS"
    }


# ============================================================
# 14. PERCENTAGE SUM CHECK (All fields)
# ============================================================

def percentage_sum_check(percentages: List[float], total_expected: float = 100.0,
                          tolerance: float = 1.0, label: str = "categories") -> dict:
    """
    Check if reported percentages sum correctly. 
    A classic fabrication tell: subgroups that don't add to 100%.
    
    Also checks for implausible precision (e.g., "33.33%, 33.33%, 33.34%")
    
    Args:
        percentages: List of reported percentages
        total_expected: Expected total (usually 100)
        tolerance: Acceptable deviation from total
        label: Description of what the percentages represent
    """
    total = sum(percentages)
    deviation = total - total_expected
    
    # Check 1: Sum deviation
    sum_ok = abs(deviation) <= tolerance
    
    # Check 2: Suspicious precision
    # If all percentages have the same number of decimal places and sum exactly...
    decimals = []
    for p in percentages:
        s = f"{p:.10f}".rstrip('0')
        if '.' in s:
            decimals.append(len(s.split('.')[1]))
        else:
            decimals.append(0)
    
    # All same precision is suspicious if they sum perfectly
    same_precision = len(set(decimals)) == 1 if decimals else False
    
    # Check 3: Equal distribution (fabricators default to equal splits)
    if len(percentages) >= 3:
        mean_pct = total / len(percentages)
        all_equal = all(abs(p - mean_pct) < 0.15 for p in percentages)
    else:
        all_equal = False
    
    issues = []
    if not sum_ok:
        issues.append(f"Percentages sum to {total:.1f}%, expected {total_expected}% (deviation: {deviation:+.1f}pp)")
    if same_precision and abs(deviation) < 0.01:
        issues.append("All percentages have identical decimal precision and sum perfectly — possible fabrication")
    if all_equal:
        issues.append("All percentages are nearly equal — possible default split by fabricator")
    
    return {
        "method": "Percentage Sum Check",
        "label": label,
        "reported_percentages": percentages,
        "total": round(total, 2),
        "expected": total_expected,
        "deviation": round(deviation, 2),
        "all_equal_split": all_equal,
        "issues": issues,
        "verdict": "RED FLAG" if len(issues) >= 2 else \
                   "WARNING" if issues else "PASS"
    }


# ============================================================
# 15. CORRELATION MATRIX CHECK (Psychology, Economics, Biology)
# ============================================================

def correlation_matrix_check(corr_matrix: List[List[float]], 
                               variable_names: List[str] = None,
                               n: int = 100) -> dict:
    """
    Check if a reported correlation matrix is mathematically possible.
    
    Requirements for a valid correlation matrix:
    1. Symmetric
    2. Diagonal = 1.0
    3. All values in [-1, 1]
    4. Positive semi-definite (all eigenvalues >= 0)
    5. No impossible correlation patterns (e.g., if r(A,B)=0.9 and r(B,C)=0.9, r(A,C) can't be 0)
    
    Args:
        corr_matrix: NxN list of lists, the reported correlation matrix
        variable_names: Optional names for variables
        n: Sample size (for partial correlation bounds)
    """
    import math
    m = len(corr_matrix)
    if variable_names is None:
        variable_names = [f"V{i+1}" for i in range(m)]
    
    issues = []
    
    # Check 1: Symmetry
    for i in range(m):
        for j in range(i+1, m):
            if abs(corr_matrix[i][j] - corr_matrix[j][i]) > 0.001:
                issues.append(f"Matrix not symmetric: r({variable_names[i]},{variable_names[j]})={corr_matrix[i][j]} vs {corr_matrix[j][i]}")
    
    # Check 2: Diagonals
    for i in range(m):
        if abs(corr_matrix[i][i] - 1.0) > 0.001:
            issues.append(f"Diagonal[{i}]={corr_matrix[i][i]}, expected 1.0")
    
    # Check 3: Bounds
    for i in range(m):
        for j in range(i+1, m):
            if abs(corr_matrix[i][j]) > 1.0:
                issues.append(f"r({variable_names[i]},{variable_names[j]})={corr_matrix[i][j]} is outside [-1,1]")
    
    # Check 4: Determinant-based positive definiteness (for small matrices)
    try:
        # Simple 3x3 triangle inequality check
        if m >= 3:
            for i in range(m):
                for j in range(i+1, m):
                    for k in range(j+1, m):
                        r12 = corr_matrix[i][j]
                        r13 = corr_matrix[i][k]
                        r23 = corr_matrix[j][k]
                        
                        # Partial correlation bound
                        det_condition = 1 + 2*r12*r13*r23 - r12**2 - r13**2 - r23**2
                        if det_condition < -0.001:
                            issues.append(
                                f"Correlation triangle impossible: "
                                f"r({variable_names[i]},{variable_names[j]})={r12:.2f}, "
                                f"r({variable_names[i]},{variable_names[k]})={r13:.2f}, "
                                f"r({variable_names[j]},{variable_names[k]})={r23:.2f} "
                                f"(determinant condition = {det_condition:.4f}, must be >= 0)"
                            )
    except:
        pass
    
    return {
        "method": "Correlation Matrix Check",
        "n_variables": m,
        "variables": variable_names,
        "n_issues": len(issues),
        "issues": issues,
        "verdict": "RED FLAG" if len(issues) >= 2 else \
                   "WARNING" if issues else "PASS"
    }


# ============================================================
# 16. ANOVA DF CHECK (Psychology, Biology, Medicine, Agriculture)
# ============================================================

def anova_df_check(f_values: List[float], df_between: List[int], df_within: List[int],
                    n_total: int = None, n_groups: int = None, label: str = "ANOVA") -> dict:
    """
    Check ANOVA degrees of freedom for internal consistency.
    
    Common fabrication errors:
    - df_between + df_within != df_total (which should be N - 1)
    - df_between != k - 1 (where k = number of groups)
    - Reported F-values inconsistent with df (e.g., F < 0)
    
    Args:
        f_values: List of F-values
        df_between: List of numerator df (between-groups)
        df_within: List of denominator df (within-groups)
        n_total: Total N (if known)
        n_groups: Number of groups (if known)
        label: Label for this ANOVA
    """
    issues = []
    
    for i, (f, dfb, dfw) in enumerate(zip(f_values, df_between, df_within)):
        # F must be >= 0
        if f < 0:
            issues.append(f"Effect {i+1}: F({dfb},{dfw}) = {f} is negative — impossible for ANOVA")
        
        # df must be positive integers
        if dfb <= 0:
            issues.append(f"Effect {i+1}: df_between = {dfb} must be positive")
        if dfw <= 0:
            issues.append(f"Effect {i+1}: df_within = {dfw} must be positive")
        
        # If F is extremely large with small df, plausible but flag for attention
        if f > 100 and dfb == 1:
            pass  # Not necessarily wrong, but notable
    
    # Check total df consistency
    if n_total is not None:
        df_total_expected = n_total - 1
        df_total_reported = sum(df_between) + df_within[0] if df_within else 0
        # Note: df_within is usually the same for all effects in a simple ANOVA
        if df_total_reported != df_total_expected:
            issues.append(
                f"df_total mismatch: reported={df_total_reported} "
                f"(expected N-1={df_total_expected} for N={n_total})"
            )
    
    # Check n_groups consistency
    if n_groups is not None:
        for i, dfb in enumerate(df_between):
            k_from_df = dfb + 1
            if k_from_df != n_groups:
                issues.append(
                    f"Effect {i+1}: df_between={dfb} implies {k_from_df} groups, "
                    f"but {n_groups} groups are reported"
                )
    
    return {
        "method": "ANOVA df Consistency Check",
        "label": label,
        "effects_checked": len(f_values),
        "issues": issues,
        "verdict": "RED FLAG" if len(issues) >= 2 else \
                   "WARNING" if issues else "PASS"
    }


# ============================================================
# 17. DUPLICATE NUMBER DETECTION (All fields)
# ============================================================

def duplicate_number_check(data_series: dict, threshold: int = 3) -> dict:
    """
    Check for suspiciously repeated identical numbers across independent variables.
    
    Fabricators often copy-paste numbers. If the exact same value (e.g., 3.47) 
    appears across independent groups/variables, it's suspicious.
    
    Also checks for:
    - Numbers differing by exactly 1 or 0.1 (increment pattern)
    - Numbers that are simple multiples of each other
    
    Args:
        data_series: dict of {label: [values]} for different independent series
        threshold: Minimum occurrences to flag
    
    Returns:
        dict with duplicate analysis
    """
    from collections import Counter
    
    all_values = []
    value_sources = {}  # value -> [source labels]
    
    for label, values in data_series.items():
        for v in values:
            v_rounded = round(v, 4)  # standardize precision
            all_values.append(v_rounded)
            if v_rounded not in value_sources:
                value_sources[v_rounded] = []
            value_sources[v_rounded].append(label)
    
    # Find values that appear across multiple independent series
    duplicates = {}
    for v, sources in value_sources.items():
        unique_sources = set(sources)
        if len(unique_sources) >= 2:
            duplicates[v] = {
                "count": len(sources),
                "sources": list(unique_sources)
            }
    
    # Count total suspicious duplicates
    suspicious = {k: v for k, v in duplicates.items() if v['count'] >= threshold}
    
    # Check for increment patterns
    sorted_vals = sorted(set(all_values))
    increments = []
    for i in range(len(sorted_vals) - 1):
        diff = sorted_vals[i+1] - sorted_vals[i]
        if diff > 0.001:
            increments.append(round(diff, 4))
    
    inc_counter = Counter(increments)
    common_increments = [(inc, cnt) for inc, cnt in inc_counter.most_common(3) if cnt >= 3]
    
    issues = []
    if suspicious:
        issues.append(f"Found {len(suspicious)} values appearing across independent series")
    if common_increments:
        issues.append(f"Suspiciously regular increments: {common_increments}")
    
    return {
        "method": "Duplicate Number Detection",
        "n_series": len(data_series),
        "n_unique_values": len(set(all_values)),
        "n_duplicates": len(duplicates),
        "n_suspicious": len(suspicious),
        "suspicious_examples": {str(k): v for k, v in list(suspicious.items())[:5]},
        "common_increments": common_increments,
        "issues": issues,
        "verdict": "RED FLAG" if len(suspicious) >= 3 else \
                   "WARNING" if suspicious else "PASS"
    }


# ============================================================
# 18. ROUNDING CONSISTENCY (All fields)
# ============================================================

def rounding_consistency(values: List[float], labels: List[str] = None) -> dict:
    """
    Check if numbers are reported with consistent and plausible rounding.
    
    Common fabrication tells:
    - All numbers to exactly 2 decimal places (fabricator's default)
    - Mismatched precision (mean to 3dp but SD to 1dp)
    - Impossible precision for measurement instrument (e.g., weight to 0.001g from bathroom scale)
    - Too many significant figures relative to sample size
    
    Args:
        values: List of numeric values
        labels: Optional labels for each value
    
    Returns:
        dict with rounding analysis
    """
    from collections import Counter
    
    precisions = []
    sig_figs = []
    
    for v in values:
        s = f"{abs(v):.12f}".rstrip('0').replace('.', '')
        if '.' in f"{abs(v):.12f}":
            dec = len(f"{abs(v):.12f}".split('.')[1].rstrip('0'))
        else:
            dec = 0
        precisions.append(dec)
        
        # Significant figures
        s_stripped = f"{abs(v):.12f}".replace('.', '').lstrip('0')
        sig_figs.append(len(s_stripped) if s_stripped else 1)
    
    prec_counter = Counter(precisions)
    
    issues = []
    
    # All same precision is suspicious
    if len(set(precisions)) == 1 and len(values) >= 5:
        issues.append(
            f"All {len(values)} values reported to exactly {precisions[0]} decimal places "
            f"— suspiciously uniform (real data has variable precision)"
        )
    
    # Too many significant figures
    avg_sf = sum(sig_figs) / len(sig_figs) if sig_figs else 0
    if avg_sf > 5:
        issues.append(f"Average {avg_sf:.1f} significant figures — implausibly precise for most instruments")
    
    # Precision mismatch between related values (e.g., mean more precise than raw data)
    if len(precisions) >= 2:
        max_prec = max(precisions)
        min_prec = min(precisions)
        if max_prec - min_prec >= 3:
            issues.append(f"Precision range: {min_prec} to {max_prec} decimal places — inconsistent reporting")
    
    return {
        "method": "Rounding Consistency Check",
        "n_values": len(values),
        "precision_distribution": dict(prec_counter.most_common()),
        "avg_significant_figures": round(avg_sf, 1),
        "issues": issues,
        "verdict": "WARNING" if issues else "PASS"
    }


# ============================================================
# 19. TABLE-TEXT CONSISTENCY (All fields)
# ============================================================

def table_text_consistency(pairs: List[dict]) -> dict:
    """
    Check if the same statistic is reported consistently in tables vs text.
    
    A classic error in fabricated papers: the same number appears differently 
    in the abstract, text, and tables because the fabricator lost track.
    
    Args:
        pairs: List of dicts, each with:
            'label': description
            'table_value': value as reported in table
            'text_value': value as reported in text
            'tolerance': acceptable difference (default 0.01)
    
    Returns:
        dict with mismatch analysis
    """
    mismatches = []
    
    for p in pairs:
        tv = p['table_value']
        xv = p['text_value']
        tol = p.get('tolerance', 0.01)
        
        if abs(tv - xv) > tol:
            mismatches.append({
                "label": p['label'],
                "table_value": tv,
                "text_value": xv,
                "difference": round(abs(tv - xv), 4),
                "pct_difference": round(abs(tv - xv) / max(abs(tv), 0.001) * 100, 1)
            })
    
    issues = []
    if mismatches:
        for m in mismatches:
            issues.append(
                f"'{m['label']}': table={m['table_value']}, text={m['text_value']} "
                f"(diff={m['difference']}, {m['pct_difference']}%)"
            )
    
    return {
        "method": "Table-Text Consistency",
        "n_pairs": len(pairs),
        "n_mismatches": len(mismatches),
        "mismatches": mismatches,
        "issues": issues,
        "verdict": "RED FLAG" if len(mismatches) >= 2 else \
                   "WARNING" if mismatches else "PASS"
    }


# ============================================================
# 20. SURVIVAL / COUNT DATA CONSISTENCY (Medicine, Epidemiology)
# ============================================================

def count_data_consistency(events: int, at_risk: int, follow_up: float = None,
                            rate: float = None, label: str = "data") -> dict:
    """
    Check count/survival data for internal consistency.
    
    Basic sanity:
    - events <= at_risk at all time points
    - Reported rate = events / at_risk (within rounding)
    - Person-time consistency if follow-up reported
    
    Args:
        events: Number of events
        at_risk: Number at risk
        follow_up: Mean follow-up time in years (optional)
        rate: Reported rate per person-year (optional)
        label: Data label
    """
    issues = []
    
    if events > at_risk:
        issues.append(f"Events ({events}) > at-risk ({at_risk}) — impossible")
    
    if events < 0 or at_risk < 0:
        issues.append("Negative count — impossible")
    
    if at_risk == 0 and events > 0:
        issues.append("Events with zero at-risk — impossible")
    
    # Rate consistency
    if rate is not None and at_risk > 0:
        crude_rate = events / at_risk
        if follow_up is not None and follow_up > 0:
            person_years = at_risk * follow_up
            person_year_rate = events / person_years
            if abs(person_year_rate - rate) / max(rate, 0.001) > 0.10:
                issues.append(
                    f"Reported rate ({rate:.4f} /py) inconsistent with "
                    f"events={events}, N={at_risk}, follow-up={follow_up}y "
                    f"(computed: {person_year_rate:.4f} /py)"
                )
    
    return {
        "method": "Count/Survival Data Consistency",
        "label": label,
        "events": events,
        "at_risk": at_risk,
        "crude_rate": round(events / at_risk, 4) if at_risk > 0 else None,
        "issues": issues,
        "verdict": "RED FLAG" if issues else "PASS"
    }


# ============================================================
# FULL AUDIT
# ============================================================

def full_audit(paper_data: dict) -> dict:
    """
    Run all applicable forensic tests on paper data.
    
    Args:
        paper_data: dict with any of:
            - 'values': list of numeric values for Benford + digit preference
            - 'descriptives': list of {mean, sd, n, label} for GRIM + sample-size sanity
            - 'p_values': list of p-values for p-curve
            - 'groups': list of {mean, sd, n, label} for summary stats consistency
            - 'mass_balance': {inputs, outputs, accumulation}
            - 'formula_params': {reported_value, ds, ...} for formula audit
            - 'mc_params': list of parameter dicts for MC sniff
    
    Returns:
        Full audit report dict
    """
    results = {}
    flags = {}
    
    if 'values' in paper_data and paper_data['values']:
        results['benford'] = benford_test(paper_data['values'])
        results['digit_preference'] = digit_preference(paper_data['values'])
        flags['benford'] = results['benford']['verdict']
        flags['digit_preference'] = results['digit_preference']['verdict']
    
    if 'descriptives' in paper_data:
        grim_results = []
        ss_results = []
        for desc in paper_data['descriptives']:
            grim_results.append(grim_test(
                desc['mean'], desc['n'], desc.get('decimal_places', 2), desc.get('label', 'var')
            ))
            ss_results.append(sample_size_sanity(
                desc['mean'], desc['sd'], desc['n'], variable_name=desc.get('label', 'var')
            ))
        results['grim'] = grim_results
        results['sample_size_sanity'] = ss_results
        
        # Summary stats consistency
        if len(paper_data['descriptives']) >= 2:
            results['stats_consistency'] = summary_stats_consistency(paper_data['descriptives'])
            flags['stats_consistency'] = results['stats_consistency']['verdict']
    
    if 'scale_check' in paper_data:
        sc = paper_data['scale_check']
        results['scale_boundary'] = scale_boundary_check(
            sc['mean'], sc['sd'], sc['min_val'], sc['max_val'],
            sc.get('n', 30), sc.get('label', 'scale')
        )
        flags['scale_boundary'] = results['scale_boundary']['verdict']
    
    if 'percentages' in paper_data:
        pc = paper_data['percentages']
        results['percentage_sum'] = percentage_sum_check(
            pc['values'], pc.get('expected', 100.0),
            pc.get('tolerance', 1.0), pc.get('label', 'categories')
        )
        flags['percentage_sum'] = results['percentage_sum']['verdict']
    
    if 'corr_matrix' in paper_data:
        cm = paper_data['corr_matrix']
        results['correlation_matrix'] = correlation_matrix_check(
            cm['matrix'], cm.get('names'), cm.get('n', 100)
        )
        flags['correlation_matrix'] = results['correlation_matrix']['verdict']
    
    if 'anova_check' in paper_data:
        av = paper_data['anova_check']
        results['anova_df'] = anova_df_check(
            av['f_values'], av['df_between'], av['df_within'],
            av.get('n_total'), av.get('n_groups'), av.get('label', 'ANOVA')
        )
        flags['anova_df'] = results['anova_df']['verdict']
    
    if 'duplicate_check' in paper_data:
        results['duplicate_numbers'] = duplicate_number_check(
            paper_data['duplicate_check']
        )
        flags['duplicate_numbers'] = results['duplicate_numbers']['verdict']
    
    if 'rounding_values' in paper_data:
        results['rounding'] = rounding_consistency(
            paper_data['rounding_values'].get('values', []),
            paper_data['rounding_values'].get('labels')
        )
        flags['rounding'] = results['rounding']['verdict']
    
    if 'table_text_pairs' in paper_data:
        results['table_text'] = table_text_consistency(
            paper_data['table_text_pairs']
        )
        flags['table_text'] = results['table_text']['verdict']
    
    if 'count_data' in paper_data:
        cd = paper_data['count_data']
        results['count_data'] = count_data_consistency(
            cd['events'], cd['at_risk'], cd.get('follow_up'),
            cd.get('rate'), cd.get('label', 'data')
        )
        flags['count_data'] = results['count_data']['verdict']
    
    if 'statcheck_list' in paper_data:
        results['statcheck'] = batch_statcheck(paper_data['statcheck_list'])
        flags['statcheck'] = results['statcheck']['verdict']
    
    if 'sprite_params' in paper_data:
        spr = paper_data['sprite_params']
        results['sprite'] = sprite_test(
            spr['mean'], spr['sd'], spr['n'],
            spr.get('m_prec', 2), spr.get('sd_prec', 2),
            spr.get('min_val', 1), spr.get('max_val', 7),
            spr.get('scale_label', '1-7')
        )
        flags['sprite'] = results['sprite']['verdict']
    
    if 'p_values' in paper_data and paper_data['p_values']:
        results['pcurve'] = pcurve_test(paper_data['p_values'])
        flags['pcurve'] = results['pcurve']['verdict']
    
    if 'groups' in paper_data and len(paper_data['groups']) >= 2:
        results['stats_consistency'] = summary_stats_consistency(paper_data['groups'])
        flags['stats_consistency'] = results['stats_consistency']['verdict']
    
    if 'mass_balance' in paper_data:
        mb = paper_data['mass_balance']
        results['mass_balance'] = mass_balance_check(
            mb.get('inputs', {}), mb.get('outputs', {}),
            mb.get('accumulation', 0), mb.get('tolerance', 0.05),
            mb.get('system_name', 'system')
        )
        flags['mass_balance'] = results['mass_balance']['verdict']
    
    if 'effect_size' in paper_data:
        es = paper_data['effect_size']
        results['effect_size'] = effect_size_consistency(
            es['mean1'], es['mean2'], es['sd_pooled'], es['reported_d']
        )
        flags['effect_size'] = results['effect_size']['verdict']
    
    if 'formula_params' in paper_data:
        cp = paper_data['formula_params']
        results['formula_check'] = formula_audit(
            cp['reported_value'], cp['input_a'],
            cp.get('factor_a', 0.65), cp.get('factor_b', 0.55), cp.get('factor_c', 0.35)
        )
        flags['formula_check'] = results['formula_check']['verdict']
    
    if 'mc_params' in paper_data:
        results['mc_sniff'] = mc_parameter_sniff(paper_data['mc_params'])
        flags['mc_sniff'] = results['mc_sniff']['verdict']
    
    # Summary
    red_count = sum(1 for v in flags.values() if 'RED FLAG' in str(v))
    warn_count = sum(1 for v in flags.values() if 'WARNING' in str(v))
    pass_count = sum(1 for v in flags.values() if str(v) == 'PASS')
    
    overall = "CRITICAL — Multiple red flags detected" if red_count >= 3 else \
              "SUSPICIOUS — Red flags present" if red_count >= 1 else \
              "CAUTION — Warnings present" if warn_count >= 2 else \
              "LARGELY PASS" if warn_count >= 1 else \
              "CLEAN — No red flags or warnings"
    
    return {
        "paper": paper_data.get('title', 'Untitled'),
        "timestamp": __import__('datetime').datetime.now().isoformat(),
        "results": results,
        "flags_summary": flags,
        "counts": {"RED FLAG": red_count, "WARNING": warn_count, "PASS": pass_count},
        "overall_verdict": overall
    }


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Academic Data Forensics Toolkit')
    sub = parser.add_subparsers(dest='command')
    
    # Full audit
    audit = sub.add_parser('audit', help='Run full audit on paper data JSON')
    audit.add_argument('--paper', required=True, help='Path to paper data JSON')
    
    # Benford
    bf = sub.add_parser('benford', help='Benford\'s Law test')
    bf.add_argument('values', help='Comma-separated values or path to CSV')
    
    # GRIM
    gm = sub.add_parser('grim', help='GRIM test')
    gm.add_argument('--mean', type=float, required=True)
    gm.add_argument('--n', type=int, required=True)
    gm.add_argument('--dp', type=int, default=2, help='Decimal places')
    gm.add_argument('--label', default='variable')
    
    # p-curve
    pc = sub.add_parser('pcurve', help='p-curve analysis')
    pc.add_argument('pvalues', help='Comma-separated p-values')
    
    # Report generation
    rpt = sub.add_parser('report', help='Generate audit report')
    rpt.add_argument('--input', required=True, help='Path to audit results JSON')
    rpt.add_argument('--output', default='audit_report.md', help='Output markdown path')
    
    args = parser.parse_args()
    
    if args.command == 'audit':
        with open(args.paper, 'r', encoding='utf-8') as f:
            paper_data = json.load(f)
        result = full_audit(paper_data)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif args.command == 'benford':
        # Parse values
        if args.values.endswith('.csv'):
            import csv
            with open(args.values) as f:
                vals = [float(r[0]) for r in csv.reader(f) if r]
        else:
            vals = [float(x.strip()) for x in args.values.split(',') if x.strip()]
        result = benford_test(vals)
        print(json.dumps(result, indent=2))
    
    elif args.command == 'grim':
        result = grim_test(args.mean, args.n, args.dp, args.label)
        print(json.dumps(result, indent=2))
    
    elif args.command == 'pcurve':
        pvals = [float(x.strip()) for x in args.pvalues.split(',') if x.strip()]
        result = pcurve_test(pvals)
        print(json.dumps(result, indent=2))
    
    elif args.command == 'report':
        with open(args.input, 'r', encoding='utf-8') as f:
            audit_data = json.load(f)
        
        # Generate markdown report
        md = generate_report_md(audit_data)
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"Report saved to {args.output}")
    
    else:
        parser.print_help()


def generate_report_md(audit_data: dict) -> str:
    """Generate a human-readable markdown audit report."""
    lines = []
    lines.append(f"# Academic Data Forensics Audit Report")
    lines.append(f"")
    lines.append(f"**Paper**: {audit_data.get('paper', 'Untitled')}")
    lines.append(f"**Timestamp**: {audit_data.get('timestamp', 'N/A')}")
    lines.append(f"")
    
    overall = audit_data.get('overall_verdict', 'Unknown')
    counts = audit_data.get('counts', {})
    lines.append(f"## Overall Verdict: **{overall}**")
    lines.append(f"")
    lines.append(f"| Flag Level | Count |")
    lines.append(f"|-----------|-------|")
    for level in ['RED FLAG', 'WARNING', 'PASS']:
        lines.append(f"| {level} | {counts.get(level, 0)} |")
    lines.append(f"")
    
    results = audit_data.get('results', {})
    
    for test_name, test_result in results.items():
        lines.append(f"---")
        lines.append(f"## {test_name.replace('_', ' ').title()}")
        lines.append(f"")
        
        if isinstance(test_result, list):
            for i, item in enumerate(test_result):
                lines.append(f"### Item {i+1}: {item.get('variable', item.get('label', ''))}")
                lines.append(f"")
                lines.append(f"**Verdict**: {item.get('verdict', 'N/A')}")
                for k, v in item.items():
                    if k not in ['verdict', 'method', 'variable', 'label', 'detail']:
                        lines.append(f"- **{k}**: {v}")
                lines.append(f"")
        elif isinstance(test_result, dict):
            verdict = test_result.get('verdict', 'N/A')
            lines.append(f"**Verdict**: {verdict}")
            lines.append(f"")
            for k, v in test_result.items():
                if k not in ['verdict', 'method', 'detail']:
                    lines.append(f"- **{k}**: {v}")
            
            # Special: Benford detail table
            if 'detail' in test_result and test_result['method'].startswith('Benford'):
                lines.append(f"")
                lines.append(f"| Digit | Observed | Expected | Obs% | Exp% |")
                lines.append(f"|-------|----------|----------|------|------|")
                for d in sorted(test_result['detail'].keys()):
                    det = test_result['detail'][d]
                    lines.append(f"| {d} | {det['observed']} | {det['expected']} | {det['observed_pct']}% | {det['expected_pct']}% |")
            lines.append(f"")
    
    return '\n'.join(lines)


if __name__ == '__main__':
    main()
