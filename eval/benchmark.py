"""
ISO/IEC 30107-3 Benchmark Evaluation Suite
Reads REAL trial data from data/telemetry_metrics.json (NO hardcoded fake numbers).
Calculates:
- Real APCER (per attack species)
- Real BPCER (genuine reject rate)
- Exact 95% Clopper-Pearson Confidence Intervals (scipy.stats.beta)
- Real p50 / p95 Latencies
"""
import os
import json
import numpy as np
from typing import Tuple, Dict, Any


def clopper_pearson(k: int, n: int, confidence: float = 0.95) -> Tuple[float, float]:
    """Computes exact Clopper-Pearson 95% confidence interval for k successes in n trials."""
    if n == 0:
        return 0.0, 1.0
    from scipy.stats import beta
    alpha = 1.0 - confidence
    lower = 0.0 if k == 0 else beta.ppf(alpha / 2.0, k, n - k + 1)
    upper = 1.0 if k == n else beta.ppf(1.0 - alpha / 2.0, k + 1, n - k)
    return float(lower), float(upper)


def run_benchmark_report(telemetry_file: str = "data/telemetry_metrics.json", output_md: str = "docs/results.md"):
    print("[Benchmark] Generating ISO/IEC 30107-3 Evaluation Report from REAL telemetry data...")

    if not os.path.exists(telemetry_file):
        scenarios = {}
        total_trials = 0
    else:
        with open(telemetry_file, "r") as f:
            data = json.load(f)
        scenarios = data.get("scenarios", {})
        total_trials = sum(sc.get("presentations", 0) for sc in scenarios.values())

    md_lines = [
        "# HID Hackathon 2026 — Presentation Attack Detection Evaluation Report",
        "",
        "> **Scope:** End-to-end decisions; these are not PAD-only APCER/BPCER measurements.  ",
        "> **Data Source:** `data/telemetry_metrics.json` (Real-world recorded trials)  ",
        f"> **Total Live Trials Recorded:** {total_trials}  ",
        "> **Latency SLA:** $\\le 2.0$ seconds  ",
        "",
        "## 1. Measured Per-Scenario Performance Matrix",
        "",
        "| Scenario | Presentations | ALLOW (Pass) | STEP-UP (Verify) | DENY (Blocked) | End-to-end rate (%) | 95% Clopper-Pearson CI | p50 Latency | p95 Latency |",
        "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |"
    ]

    if total_trials == 0:
        md_lines.append("| *Awaiting Trials* | 0 | 0 | 0 | 0 | N/A | N/A | -- ms | -- ms |")
        md_lines.extend([
            "",
            "> ⚠️ **Notice:** No live webcam presentations have been recorded yet in `data/telemetry_metrics.json`.",
            "> Start the kiosk (`python run_kiosk.py`), test genuine and spoof presentations via the UI, then rerun this script.",
        ])
    else:
        for name, sc in scenarios.items():
            n = sc.get("presentations", 0)
            if n == 0:
                continue
            allow = sc.get("allow", 0)
            step_up = sc.get("request", 0)
            deny = sc.get("deny", 0)
            lats = sc.get("latencies_ms", [])
            p50 = float(np.percentile(lats, 50)) if lats else 0.0
            p95 = float(np.percentile(lats, 95)) if lats else 0.0

            if name == "genuine_live":
                bpcer = (deny / float(n)) * 100.0
                ci_low, ci_high = clopper_pearson(deny, n)
                rate_str = f"**DENY rate: {bpcer:.1f}%**"
            else:
                apcer = (allow / float(n)) * 100.0
                ci_low, ci_high = clopper_pearson(allow, n)
                rate_str = f"**ALLOW rate: {apcer:.1f}%**"

            ci_str = f"[{ci_low*100:.1f}%, {ci_high*100:.1f}%]"
            md_lines.append(f"| `{name}` | {n} | {allow} | {step_up} | {deny} | {rate_str} | {ci_str} | {p50:.0f} ms | {p95:.0f} ms |")

    md_lines.extend([
        "",
        "## 2. Real Architecture Guarantees",
        "",
        "- **Spoof veto:** A detected attack cannot be granted access. Detection accuracy requires measured trials.",
        "- **Context-Aware Schedule Check:** Biometric match is cross-referenced with campus access schedules; unauthorized shifts are denied.",
        "- **Offline queue:** Events remain pending; no central server synchronization is implemented.",
        "- **Statistical Discipline:** All error bounds report Clopper-Pearson exact intervals without tuning thresholds on test data.",
    ])

    os.makedirs(os.path.dirname(output_md), exist_ok=True)
    with open(output_md, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))

    print(f"[Benchmark] Report generated from real data at {output_md}")


if __name__ == "__main__":
    run_benchmark_report()
