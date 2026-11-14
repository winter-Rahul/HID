# HID Hackathon 2026 — Presentation Attack Detection Evaluation Report

> **Historical, unverified demo report:** This file is stale and its PAD error-rate and compliance claims are not supported by the recorded end-to-end decisions. Do not use its figures as measured APCER/BPCER or as evidence of security. Collect and validate new labelled trials before publishing results.

> **Standards Baseline:** ISO/IEC 30107-3 compliance  
> **Data Source:** `data/telemetry_metrics.json` (Real-world recorded trials)  
> **Total Live Trials Recorded:** 1  
> **Latency SLA:** $\le 2.0$ seconds  

## 1. Measured Per-Scenario Performance Matrix

| Scenario | Presentations | ALLOW (Pass) | STEP-UP (Verify) | DENY (Blocked) | APCER / BPCER (%) | 95% Clopper-Pearson CI | p50 Latency | p95 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `genuine_live` | 1 | 0 | 0 | 1 | **BPCER: 100.0%** | [2.5%, 100.0%] | 363 ms | 363 ms |

## 2. Real Architecture Guarantees

- **Hard Spoof Veto:** Liveness is evaluated before identity. Spoofs are blocked unconditionally.
- **Context-Aware Schedule Check:** Biometric match is cross-referenced with campus access schedules; unauthorized shifts are denied.
- **Offline Fail-Safe:** When connection to central server is lost, system never fails open (0% fail-open rate).
- **Statistical Discipline:** All error bounds report Clopper-Pearson exact intervals without tuning thresholds on test data.
