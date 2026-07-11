---
name: truthtracer
description: >-
  Academic risk early-warning system. Audits papers for statistical anomalies,
  tortured phrases, citation integrity, and author network signals. Generates
  traceable evidence chains. RIGID-framework-inspired. Use when the user asks
  to audit, investigate, or forensically examine a paper.
version: 2.3.0
metadata:
  hermes:
    tags: [academic-integrity, fraud-detection, research-forensics, peer-review,
           data-audit, evidence-chain, risk-assessment]
    category: research
---

# TruthTracer

> Don't ask whether a paper is fraudulent. Ask where the evidence stops supporting the claims.

---

## When to Use

Load this skill when the user asks to:

- "audit this paper" / "check this paper for fraud" / "forensic analysis"
- "investigate this author" / "look into this researcher"
- "scan for tortured phrases" / "check for AI-generated text in this paper"
- "verify the statistics in this paper" / "are these numbers real"
- "run TruthTracer on…"

---

## How to Use

### Step 1: Gather the paper

Ask the user for one of:
- A PDF file path
- A plain-text extraction of the paper
- A DOI or paper title (for network investigation only)

If the user provides a PDF, extract text first:

```bash
python scripts/extract_pdf.py <pdf_path> <output_txt>
```

### Step 2: Run the audit

Choose the appropriate engine based on what the user needs:

| User asks for | Command |
|---------------|---------|
| Full audit | `python scripts/scorer.py --stats <stats_json> --network <network_json> --output report.md` |
| Stats only | `python scripts/forensics.py audit --paper <data.json> > audit.json` |
| Text check | `python scripts/text_engine.py check <text_file>` |
| Author check | `python scripts/network_engine.py investigate "Author Name" --deep` |

### Step 3: Present findings

Summarize the results for the user in plain language:

1. **Risk level** — CRITICAL / HIGH / MEDIUM / LOW / CLEAN
2. **Top 3 signals** — what flagged and why
3. **Evidence chain** — where the data stops supporting the claims
4. **Recommendation** — what action to take (request raw data, cross-check, etc.)

Always remind the user: *TruthTracer flags risks, not verdicts. Human judgment required.*

---

## Risk Framework

| Level | Criteria | Action |
|-------|----------|--------|
| CRITICAL | 2+ mathematical impossibilities | Escalate to ethics committee |
| HIGH | 1 impossibility OR multiple strong signals | Request raw data |
| MEDIUM | Anomalies, no impossibilities | Request clarification |
| LOW | Minor pattern anomalies | Standard peer review |
| CLEAN | No signals | Proceed |

**Golden rule**: Zero CRITICAL signals caps risk at MEDIUM. Only mathematical impossibility constitutes near-certain fraud.

---

## Paper-Type Awareness

The scorer automatically adjusts based on paper type:

| Type | Detected by | Adjustment |
|------|------------|------------|
| Economic/LCA models | cost, techno-economic, scenario, LCA, US$ | Benford/digit checks → 30% weight |
| Clinical trials | patients, trial, hazard ratio, survival | Survival checks → 150% weight |
| Experimental | experiment, randomized, p <, t-test | Full weight on all tests |
| Reviews | review, meta-analysis, systematic | Skip statistical tests |

---

## Tool Reference

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/scorer.py` | Evidence fusion + report generation | `--stats <json> --network <json> --output <md>` |
| `scripts/forensics.py` | 21 statistical methods | `audit --paper <json>` |
| `scripts/investigator.py` | 10 network signals | `investigate "Name" --deep` |
| `scripts/text_engine.py` | Tortured phrases, AI patterns | `check <file>` |
| `scripts/network_engine.py` | Author network analysis | `investigate "Name" --deep` |
| `scripts/citation_engine.py` | Citation integrity | `audit <doi>` |
| `scripts/supplement_engine.py` | SI completeness | `audit <doi>` |
| `scripts/preprint_engine.py` | Preprint comparison | `compare <preprint_doi> <published_doi>` |
| `scripts/distribution_engine.py` | Dispersion patterns | `check <data>` |
| `scripts/extract_pdf.py` | PDF text extraction | `<pdf> [output]` |

---

## References

- RIGID Framework: doi:10.1016/j.eclinm.2024.102717
- Tortured phrases detection: adapted from Cabanac et al. (2021), arXiv:2107.06751
- GRIM + SPRITE: adapted from QuentinAndre/pysprite (MIT)
- 29 of 31 statistical methods are original implementations
