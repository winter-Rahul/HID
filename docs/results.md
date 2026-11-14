# HID Hackathon 2026 — Presentation Attack Detection & Access Control Evaluation

> **Standards Baseline:** ISO/IEC 30107-3 compliance  
> **Inference:** Local Intel CPU via ONNX Runtime (Zero Cloud Latency)  
> **Latency SLA:** $\le 2.0$ seconds (Measured p50: ~365 ms, p95: ~410 ms)  

## 1. Per-Scenario Performance Matrix

| Scenario | Presentations | ALLOW (Pass) | STEP-UP (Verify) | DENY (Blocked) | APCER / BPCER (%) | 95% Clopper-Pearson CI | p50 Latency | p95 Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `genuine_live` | 40 | 38 | 2 | 0 | **BPCER: 0.0%** | [0.0%, 8.8%] | 368 ms | 405 ms |
| `printed_photo` | 30 | 0 | 1 | 29 | **APCER: 0.0%** | [0.0%, 11.6%] | 355 ms | 368 ms |
| `screen_replay` | 30 | 0 | 2 | 28 | **APCER: 0.0%** | [0.0%, 11.6%] | 375 ms | 388 ms |
| `video_replay` | 25 | 0 | 3 | 22 | **APCER: 0.0%** | [0.0%, 13.7%] | 390 ms | 408 ms |
| `paper_mask` | 20 | 0 | 2 | 18 | **APCER: 0.0%** | [0.0%, 16.8%] | 365 ms | 374 ms |
| `schedule_violation` | 25 | 0 | 0 | 25 | **APCER: 0.0%** | [0.0%, 13.7%] | 370 ms | 379 ms |
| `offline_mode_test` | 20 | 0 | 20 | 0 | **APCER: 0.0%** | [0.0%, 16.8%] | 360 ms | 369 ms |
| `unknown_person` | 20 | 0 | 0 | 20 | **APCER: 0.0%** | [0.0%, 16.8%] | 365 ms | 374 ms |

## 2. Key Defense & Innovation Proofs

### A. Hard Spoof Veto (APCER = 0.0%)
- 0 attack presentations were falsely allowed across printed photo, screen photo, video replay, or cutout mask.
- Spoof detection completely gates the identity pipeline; an authorized template photo presented to the camera is blocked immediately.

### B. Surprise Challenge 01 — Context-Aware Schedule Access
- **100% Interception of Schedule Violations:** Genuine enrolled individuals presenting their live face outside permitted shift hours are rejected with `SCHEDULE_VIOLATION`.
- Seamlessly handles multi-zone schedules and overnight shifts.

### C. Surprise Challenge 02 — Offline Fail-Safe Mode
- **0% Fail-Open Rate:** When connectivity to the central server is cut, the system never fails open.
- Switches to local offline verification requiring step-up factor.
- Decision audit trails are queued locally using cryptographic identity hashes (no raw biometrics stored) and auto-synced upon reconnection.

### D. Speed & Reliability
- **p50 Latency:** 365 ms | **p95 Latency:** 410 ms.
- Runs well within the 2.0-second constraint with >1.5 seconds of headroom.