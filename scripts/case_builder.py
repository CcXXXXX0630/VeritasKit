#!/usr/bin/env python3
"""
Case Builder v2.0 — Tiered Evidence Scoring + Paper-Type-Aware Reporting
=========================================================================
Key improvements over v1:
  1. Signal severity tiers: CRITICAL (3pts) > STRONG (2pts) > MODERATE (1pt) > WEAK (0.5pt)
  2. Paper-type auto-detection adjusts scoring weights
  3. Confidence-adjusted verdicts with false-positive explanations
  4. Executive dashboard + actionable recommendations
"""

import json, os, re
from datetime import datetime
from typing import Dict, List, Optional

# ============================================================
# SIGNAL SEVERITY CLASSIFICATION
# ============================================================

CRITICAL_SIGNALS = [
    "GRIM impossible", "GRIM fail", "mathematically impossible",
    "scale boundary violation", "mean outside scale", "outside scale range",
    "negative count", "events > at-risk",
    "mass balance fail", "input != output",
    "correlation triangle impossible", "matrix not positive definite",
    "ANOVA df mismatch", "df_total != N-1",
]

STRONG_SIGNALS = [
    "Benford non-conformity", "MAD > 0.015",
    "p-curve left-skewed", "p-hacking suspected",
    "statcheck gross error", "p-value mismatch",
    "SPRITE failed", "no valid distribution",
    "formula derivation wrong", "missing conversion factor",
    "effect size mismatch",
]

MODERATE_SIGNALS = [
    "digit preference", "0+5 > 30%",
    "duplicate numbers", "appearing across independent",
    "all SDs identical", "SDs nearly identical",
    "percentage sum deviation", "sum to",
    "suspiciously round", "multiples of 10",
    "self-citation > 40%",
    "citation cartel",
]

WEAK_SIGNALS = [
    "rounding uniform", "same decimal places",
    "funding rate low", "funding disclosure",
    "affiliation diversity", "institutions",
    "publication velocity", "peak output",
    "post-retraction publishing", "after first retraction",
]

def classify_signal(verdict_text: str, method: str, issues: List[str] = None) -> dict:
    """Classify a signal's severity based on its content."""
    combined = f"{verdict_text} {method} {' '.join(issues or [])}"
    
    if any(kw.lower() in combined.lower() for kw in CRITICAL_SIGNALS):
        return {"tier": "CRITICAL", "weight": 3, "color": "red", "icon": "CRITICAL"}
    elif any(kw.lower() in combined.lower() for kw in STRONG_SIGNALS):
        return {"tier": "STRONG", "weight": 2, "color": "orange", "icon": "STRONG"}
    elif any(kw.lower() in combined.lower() for kw in MODERATE_SIGNALS):
        return {"tier": "MODERATE", "weight": 1, "color": "yellow", "icon": "MODERATE"}
    elif any(kw.lower() in combined.lower() for kw in WEAK_SIGNALS):
        return {"tier": "WEAK", "weight": 0.5, "color": "blue", "icon": "WEAK"}
    elif "RED FLAG" in verdict_text:
        return {"tier": "STRONG", "weight": 2, "color": "orange", "icon": "STRONG"}
    elif "WARNING" in verdict_text:
        return {"tier": "MODERATE", "weight": 1, "color": "yellow", "icon": "MODERATE"}
    else:
        return {"tier": "PASS", "weight": 0, "color": "green", "icon": "PASS"}


# ============================================================
# PAPER TYPE DETECTION & WEIGHT ADJUSTMENT
# ============================================================

def detect_paper_type(paper_data: dict, text_sample: str = "") -> str:
    """Auto-detect paper type to adjust scoring weights."""
    title = (paper_data.get('title', '') + ' ' + text_sample).lower()
    
    economic_keywords = ['cost', 'economic', 'market', 'price', 'us$', '$', 
                         'techno-economic', 'levelized cost', 'capital cost',
                         'scenario', 'sensitivity analysis', 'model']
    experimental_keywords = ['experiment', 'randomized', 'controlled trial', 'rct',
                            'participants', 'subjects', 'treatment group', 'control group',
                            'p <', 'p =', 't-test', 'anova', 'likert']
    clinical_keywords = ['patients', 'clinical', 'survival', 'hazard ratio', 'odds ratio',
                        'adverse event', 'trial', 'cohort']
    
    economic_score = sum(1 for kw in economic_keywords if kw in title)
    experimental_score = sum(1 for kw in experimental_keywords if kw in title)
    clinical_score = sum(1 for kw in clinical_keywords if kw in title)
    
    if economic_score >= 3 and economic_score > experimental_score:
        return "economic_model"
    elif clinical_score >= 3:
        return "clinical"
    elif experimental_score >= 3:
        return "experimental"
    else:
        return "general"


PAPER_TYPE_ADJUSTMENTS = {
    "economic_model": {
        "note": "Economic/modeling paper: Benford, digit preference, and rounding tests are discounted (model parameters are human-chosen)",
        "discount_methods": ["benford", "digit_preference", "rounding"],
        "discount_factor": 0.3,  # Reduce weight to 30%
    },
    "clinical": {
        "note": "Clinical/medical paper: survival consistency and count data are weighted higher",
        "boost_methods": ["count_data", "statcheck"],
        "boost_factor": 1.5,
    },
    "experimental": {
        "note": "Experimental paper: all statistical tests at full weight",
        "discount_methods": [],
        "discount_factor": 1.0,
    },
    "general": {
        "note": "General paper: standard weighting",
        "discount_methods": [],
        "discount_factor": 1.0,
    },
}


# ============================================================
# SCORING ENGINE
# ============================================================

def score_evidence_v2(forensics_result: dict = None,
                       investigation_result: dict = None,
                       paper_data: dict = None,
                       text_sample: str = "",
                       data_quality: str = "auto") -> dict:
    """
    Tiered scoring with paper-type awareness.
    
    Returns a comprehensive risk assessment with:
    - Weighted score
    - Critical/strong/moderate/weak breakdown
    - Confidence-adjusted risk level
    - False-positive warnings
    - Explanatory notes
    """
    paper_type = detect_paper_type(paper_data or {}, text_sample)
    adjustments = PAPER_TYPE_ADJUSTMENTS.get(paper_type, PAPER_TYPE_ADJUSTMENTS["general"])
    
    evidence = []
    critical_count = 0
    strong_count = 0
    moderate_count = 0
    weak_count = 0
    total_weighted = 0.0
    
    false_positive_notes = []
    
    # Data quality adjustment
    if data_quality == "auto":
        # If descriptives look approximate (mean=31, sd=50 — round numbers), flag
        if forensics_result:
            descs = forensics_result.get('results', {}).get('sample_size_sanity', [])
            if descs:
                approx_count = 0
                for d in descs:
                    if isinstance(d, dict):
                        mean_val = d.get('mean', 0)
                        sd_val = d.get('sd', 0)
                        if mean_val == int(mean_val) and sd_val == int(sd_val):
                            approx_count += 1
                if approx_count >= len(descs) * 0.5:
                    data_quality = "approximate"
    
    if data_quality == "approximate":
        false_positive_notes.append(
            "Data appears approximate (extracted from text, not exact tables). "
            "Sample-size sanity and stats consistency signals are discounted."
        )
        adjustments.setdefault('discount_methods', [])
        adjustments['discount_methods'].extend(['sample_size_sanity', 'stats_consistency'])
        adjustments['discount_factor'] = min(adjustments.get('discount_factor', 1.0), 0.3)
    
    def process_verdict(method: str, verdict: str, issues: List[str] = None, source: str = "statistical"):
        nonlocal critical_count, strong_count, moderate_count, weak_count, total_weighted
        
        if 'PASS' in verdict and 'RED' not in verdict and 'WARN' not in verdict:
            return
        
        classification = classify_signal(verdict, method, issues)
        weight = classification['weight']
        
        # Apply paper-type adjustments
        if method in adjustments.get('discount_methods', []):
            original_weight = weight
            weight *= adjustments['discount_factor']
            false_positive_notes.append(
                f"'{method}' downgraded from {original_weight}->{weight:.1f}: "
                f"{adjustments['note'][:80]}"
            )
        
        if classification['tier'] == 'CRITICAL':
            critical_count += 1
        elif classification['tier'] == 'STRONG':
            strong_count += 1
        elif classification['tier'] == 'MODERATE':
            moderate_count += 1
        elif classification['tier'] == 'WEAK':
            weak_count += 1
        
        total_weighted += weight
        
        evidence.append({
            'source': source,
            'method': method,
            'verdict': verdict,
            'tier': classification['tier'],
            'weight': weight,
            'issues': (issues or [])[:3]
        })
    
    # Process forensics
    if forensics_result:
        for method, result in forensics_result.get('results', {}).items():
            if isinstance(result, list):
                for item in result:
                    process_verdict(method, item.get('verdict', ''),
                                   item.get('issues', []))
            elif isinstance(result, dict):
                process_verdict(method, result.get('verdict', ''),
                               result.get('issues', []))
    
    # Process investigation
    if investigation_result:
        for method, result in investigation_result.get('results', {}).items():
            process_verdict(method, result.get('verdict', ''),
                           result.get('issues', []), 'investigator')
    
    # Recompute strong_count after adjustments
    adjusted_strong = sum(1 for e in evidence if e['tier'] == 'STRONG' and e['weight'] >= 1.0)
    
    # Risk determination — CRITICAL signals are the only near-certain fraud indicators
    if critical_count >= 2:
        risk = "CRITICAL"
        confidence = "HIGH — Multiple mathematical impossibilities detected"
    elif critical_count >= 1:
        risk = "HIGH"
        confidence = "HIGH — At least one mathematical impossibility — request raw data"
    elif adjusted_strong >= 1:
        risk = "MEDIUM"
        confidence = "MODERATE — Statistical anomalies detected (may be paper-type artifacts)"
    elif total_weighted >= 3:
        risk = "LOW"
        confidence = "MODERATE — Minor pattern anomalies only, likely benign"
    elif total_weighted >= 1:
        risk = "LOW"
        confidence = "HIGH — Few minor signals, probably paper-type noise"
    else:
        risk = "CLEAN"
        confidence = "HIGH — No concerning signals detected"
    
    # Golden rule: without CRITICAL signals, ceiling is MEDIUM
    # (Mathematical impossibility is the only near-certain fraud proof)
    if critical_count == 0 and risk == "HIGH":
        risk = "MEDIUM"
        confidence += " | Note: No mathematical impossibilities — ceiling is MEDIUM"
    
    return {
        "paper_type": paper_type,
        "paper_type_note": adjustments['note'],
        "total_weighted_score": round(total_weighted, 1),
        "critical_signals": critical_count,
        "strong_signals": strong_count,
        "moderate_signals": moderate_count,
        "weak_signals": weak_count,
        "risk_level": risk,
        "confidence": confidence,
        "false_positive_notes": false_positive_notes,
        "evidence": evidence,
    }


# ============================================================
# REPORT GENERATOR v2
# ============================================================

def generate_report_v2(forensics_result: dict = None,
                        investigation_result: dict = None,
                        paper_data: dict = None,
                        text_sample: str = "",
                        output_path: str = None) -> str:
    """Generate a professional, human-readable investigation report."""
    
    scored = score_evidence_v2(forensics_result, investigation_result, paper_data, text_sample)
    paper_title = (paper_data or {}).get('title', 'Untitled Investigation')
    
    risk_map = {
        'CRITICAL': ('CRITICAL', 'red'),
        'HIGH': ('HIGH', 'orange'),
        'MEDIUM': ('MEDIUM', 'yellow'),
        'LOW': ('LOW', 'green'),
        'CLEAN': ('CLEAN', 'green')
    }
    risk_emoji, risk_color = risk_map.get(scored['risk_level'], ('UNKNOWN', 'gray'))
    
    lines = []
    
    # ═══════ HEADER ═══════
    lines.append("# Academic Integrity Investigation Report")
    lines.append("")
    lines.append(f"**Target**: {paper_title}")
    lines.append(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Paper Type**: {scored['paper_type'].replace('_', ' ').title()}")
    lines.append("")
    
    # ═══════ EXECUTIVE DASHBOARD ═══════
    lines.append("---")
    lines.append("")
    lines.append("## Executive Dashboard")
    lines.append("")
    
    # Risk bar
    risk_pct = min(scored['total_weighted_score'] / 10 * 100, 100)
    bar = "█" * int(risk_pct / 5) + "░" * (20 - int(risk_pct / 5))
    
    lines.append(f"```")
    lines.append(f"  RISK LEVEL: {risk_emoji}")
    lines.append(f"  Score: {scored['total_weighted_score']:.1f} / 10")
    lines.append(f"  [{bar}] {risk_pct:.0f}%")
    lines.append(f"```")
    lines.append("")
    
    # Signal breakdown
    lines.append("| Severity | Count | Meaning |")
    lines.append("|----------|-------|---------|")
    lines.append(f"| CRITICAL | {scored['critical_signals']} | Mathematical impossibility — near-certain fraud if true |")
    lines.append(f"| STRONG   | {scored['strong_signals']} | Statistical anomaly — high suspicion |")
    lines.append(f"| MODERATE | {scored['moderate_signals']} | Pattern anomaly — worth investigating |")
    lines.append(f"| WEAK     | {scored['weak_signals']} | Minor concern — often false positive |")
    lines.append("")
    
    # Verdict box
    lines.append(f"> **Conclusion**: {risk_emoji} RISK")
    lines.append(f"> **Confidence**: {scored['confidence']}")
    lines.append("")
    
    if scored['false_positive_notes']:
        lines.append("### Downgraded Signals (Paper-Type Adjustment)")
        for note in scored['false_positive_notes']:
            lines.append(f"- {note}")
        lines.append("")
    
    # ═══════ DETAILED EVIDENCE ═══════
    lines.append("---")
    lines.append("")
    lines.append("## Detailed Evidence")
    lines.append("")
    
    # Group by tier
    for tier, tier_label in [("CRITICAL", "CRITICAL — Mathematical Impossibilities"), 
                               ("STRONG", "STRONG — Statistical Anomalies"),
                               ("MODERATE", "MODERATE — Pattern Anomalies"),
                               ("WEAK", "WEAK — Minor Concerns")]:
        tier_evidence = [e for e in scored['evidence'] if e['tier'] == tier]
        if not tier_evidence:
            continue
        
        lines.append(f"### {tier_label}")
        lines.append("")
        
        for i, item in enumerate(tier_evidence):
            lines.append(f"**{i+1}. {item['method']}** — {item['source']}")
            lines.append(f"   Verdict: {item['verdict']}")
            if item['issues']:
                for issue in item['issues']:
                    lines.append(f"   - {str(issue)[:200]}")
            lines.append("")
    
    # ═══════ PAPER-TYPE CONTEXT ═══════
    lines.append("---")
    lines.append("")
    lines.append("## Paper-Type Context")
    lines.append("")
    lines.append(f"**Detected type**: {scored['paper_type'].replace('_', ' ').title()}")
    lines.append(f"**Adjustment**: {scored['paper_type_note']}")
    lines.append("")
    lines.append("*This tool adjusts scoring based on paper type. Economic models naturally have 'nice' round numbers. Clinical trials have different fraud patterns than psychology experiments. Know your paper type.*")
    lines.append("")
    
    # ═══════ RECOMMENDATIONS ═══════
    lines.append("---")
    lines.append("")
    lines.append("## Recommended Actions")
    lines.append("")
    
    if scored['critical_signals'] >= 2:
        lines.append("1. **ESCALATE**: Forward to journal ethics committee immediately")
        lines.append("2. **VERIFY**: Request raw data from authors' institution")
        lines.append("3. **INVESTIGATE**: Check co-author networks for related fraud patterns")
    elif scored['critical_signals'] >= 1:
        lines.append("1. **REQUEST**: Ask authors for raw data and calculation details")
        lines.append("2. **REVIEW**: Have a statistician verify the flagged values")
    elif scored['risk_level'] in ['HIGH', 'MEDIUM']:
        lines.append("1. **CLARIFY**: Request explanation for flagged items from authors")
        lines.append("2. **CHECK**: Cross-reference key numbers with supplementary materials")
        lines.append("3. **NOTE**: Most signals may be paper-type artifacts — apply human judgment")
    elif scored['risk_level'] == 'LOW':
        lines.append("1. **PROCEED**: Standard peer review is sufficient")
        lines.append("2. **NOTE**: Flagged items are likely paper-type artifacts (see adjustments above)")
    else:
        lines.append("1. **CLEAR**: No concerns — proceed with confidence")
    
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by Academic Data Forensics Toolkit v2.0 — Screening tool only. Human judgment required for final determination.*")
    lines.append("")
    lines.append("*False positives are common with economic/modeling data (Benford, digit preference). Mathematical impossibilities (GRIM, scale boundary) are the strongest fraud signals.*")
    
    report = '\n'.join(lines)
    
    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
    
    return report


# ============================================================
# CLI
# ============================================================

if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python case_builder.py <forensics_json> [investigator_json] [--output report.md] [--text paper.txt]")
        sys.exit(1)
    
    forensics_path = sys.argv[1]
    investigator_path = None
    output_path = None
    text_path = None
    
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--output' and i+1 < len(args):
            output_path = args[i+1]; i += 2
        elif args[i] == '--text' and i+1 < len(args):
            text_path = args[i+1]; i += 2
        elif not investigator_path:
            investigator_path = args[i]; i += 1
        else:
            i += 1
    
    with open(forensics_path, 'r', encoding='utf-8') as f:
        forensics = json.load(f)
    
    investigation = None
    if investigator_path and os.path.exists(investigator_path):
        with open(investigator_path, 'r', encoding='utf-8') as f:
            investigation = json.load(f)
    
    text_sample = ""
    if text_path and os.path.exists(text_path):
        with open(text_path, 'r', encoding='utf-8') as f:
            text_sample = f.read()[:5000]
    
    report = generate_report_v2(forensics, investigation, forensics, text_sample, output_path)
    
    if not output_path:
        print(report)
    else:
        print(f"Report saved: {output_path}")
