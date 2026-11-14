# HID Hackathon 2026 — "Can You Spot a Spoof?"

> **Liveness Detection + Face Authentication Kiosk**  
> Status: 🟡 In Progress · Research complete · Implementation starting

---

## 🎯 Challenge Summary

Build a **kiosk prototype** that runs the full pipeline:

```
Capture → Liveness Check → Face Authentication → Decision (ALLOW / REQUEST VERIFICATION / DENY)
```

**Requirements:**
- ⏱ Complete pipeline in **≤ 2 seconds**
- 🎭 Demonstrate against **at least 2 spoof types** (print, screen replay, video, paper mask)
- 📊 Show **per-scenario results**: accuracy, false acceptance/rejection, decision time
- ❓ Handle **low-confidence cases** with a third "REQUEST VERIFICATION" state (recapture, OTP, or simple action)

---

## 🏗 Architecture — "Architecture B-lite" (Recommended)

```
┌─────────────┐     ┌──────────────────────────────────────┐     ┌──────────────────┐
│  Webcam      │────▶│  Passive PAD Ensemble (8–10 frames,  │────▶│  Decision Engine │
│  (RGB only)  │     │  ~0.7 s burst, ONNX Runtime)         │     │  (3-state output)│
└─────────────┘     └──────────────────────────────────────┘     └──────────────────┘
                             │                                             │
                             ▼                                             ▼
                    ┌─────────────────┐                        ALLOW / REQUEST VERIFICATION
                    │ Face Recognition│                             / DENY
                    │   Pipeline      │
                    └─────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │  AWS (S3 +      │
                    │  CloudWatch +   │
                    │  Dashboard)     │
                    └─────────────────┘
```

**Key design decisions:**

| Property | Choice | Reason |
|----------|--------|--------|
| Sensor | RGB-only webcam | 2 s budget; no IR/depth hardware |
| PAD strategy | Passive ensemble over short burst | No active challenge needed; faster |
| Temporal logic | 8–10 frames ~0.7 s, aggregate scores | Avoids single-frame false spikes |
| Decision states | ALLOW / REQUEST VERIFICATION / DENY | Covers uncertainty honestly |
| Hard veto | Spoof flag blocks identity even on match | Security-first pipeline |
| Inference | ONNX Runtime (warm sessions) | Low latency, kiosk-friendly |
| Backend | AWS S3 + CloudWatch | Logs, metrics, dashboard |

**Fallback — Architecture A:** Same models, single-best-frame, no temporal logic. Used as baseline in ablation study.

---

## 💡 Innovations We Can Defend

1. **Uncertainty-aware tri-state decisions** — evaluated with a selective-risk protocol measuring what fraction of genuine users get escalated per APCER level.
2. **Nonce-based screen-light challenge** — used *only* on the escalation path; a pre-recorded replay cannot answer it, defeating video replay attacks without slowing the happy path.

---

## 📊 Judging Criteria & Our Strategy

| Criterion | Weight | What Wins | Our Plan |
|-----------|--------|-----------|----------|
| Problem-solution fit | 25% | Show we solve *spoofing*, not just recognition | Liveness is a separate, vetoing module; per-attack results; identity never overrides a spoof flag |
| Innovation | 20% | A defensible, measurable idea over a baseline | Uncertainty-routed tri-state decision + nonce light challenge, with an ablation table |
| Technical implementation | 25% | Feasible, modular, uses APIs/frameworks, scalable | ONNX Runtime kiosk, FastAPI service, S3/CloudWatch, reproducible eval scripts |
| Functionality & usability | 15% | A working live demo | Webcam UI mirroring the poster, with latency and reason codes |
| Presentation | 15% | Clear to non-technical judges, strong Q&A | Stage-by-stage story, per-scenario table, prepared answers |

> **Lowest-risk strategy:** A demo that never crashes + a results table with honest confidence intervals + a clear statement of what the system *cannot* do.

---

## 📐 Metrics We Report

| Metric | Definition | Note |
|--------|-----------|------|
| **APCER** (per attack species *s*) | Attack presentations classified as bona fide ÷ all presentations of *s* | Report **worst species**, not the average |
| **BPCER** | Genuine presentations classified as attack ÷ all genuine | |
| **ACER** | (APCER + BPCER) / 2 | Summary only; hides worst attack |
| **EER** | Operating point where APCER = BPCER | Honest only if threshold set on dev set |
| **Genuine escalation rate** | Genuine users routed to REQUEST VERIFICATION | Friction but not a false reject |
| **Attack escalation rate** | Attacks routed to REQUEST VERIFICATION | Safe, not an acceptance |

> ⚠️ **Statistics discipline:** Use Clopper-Pearson intervals, bootstrap over *subjects* (not frames), never tune thresholds on the test set.

---

## 🗂 Project Structure

```
HID/
├── README.md
├── data/                    # Evaluation datasets (CelebA-Spoof, custom recordings)
├── models/                  # ONNX model artifacts
│   ├── pad_ensemble/        # Passive anti-spoofing models
│   └── face_recognition/    # Face embedding model
├── src/
│   ├── capture/             # Webcam capture & frame extraction
│   ├── liveness/            # PAD ensemble inference
│   ├── identity/            # Face recognition & matching
│   ├── decision/            # 3-state decision engine
│   ├── challenge/           # Nonce-based screen-light challenge
│   └── api/                 # FastAPI service
├── ui/                      # Kiosk frontend (webcam UI)
├── eval/                    # Reproducible evaluation scripts
├── aws/                     # CloudWatch / S3 logging config
└── docs/
    └── research.pdf         # HID Hackathon 2026 research brief
```

---

## 🗓 Implementation Plan (10 Days)

### Phase 1 — Foundation (Days 1–2)
- [ ] Set up repo structure, Python env, ONNX Runtime
- [ ] Integrate webcam capture module (OpenCV, 8–10 frame burst)
- [ ] Download/prepare base PAD model (MobileNetV2 or similar lightweight backbone)
- [ ] AWS S3 + CloudWatch logging skeleton

### Phase 2 — Core Pipeline (Days 3–4)
- [ ] PAD ensemble inference + frame aggregation scoring
- [ ] Face recognition pipeline (ArcFace or FaceNet, ONNX)
- [ ] 3-state decision engine with configurable thresholds
- [ ] Hard spoof veto logic (spoof flag blocks identity match)
- [ ] FastAPI service wrapping the pipeline

### Phase 3 — Innovation Layer (Days 5–6)
- [ ] Uncertainty-aware routing (entropy / confidence score → escalation)
- [ ] Nonce-based screen-light challenge for escalation path
- [ ] Ablation table: Arch A (single frame) vs Arch B-lite (temporal ensemble)

### Phase 4 — UI + Evaluation (Days 7–8)
- [ ] Kiosk webcam UI (latency display, decision code, confidence)
- [ ] Evaluation scripts: per-scenario APCER/BPCER, Clopper-Pearson CIs
- [ ] Test against ≥ 2 spoof types: printed photo + screen/video replay
- [ ] (Stretch) Paper/printed mask testing

### Phase 5 — Polish + Presentation (Days 9–10)
- [ ] Dashboard on CloudWatch for metrics
- [ ] Demo hardening (never-crash mode, fallback to Arch A)
- [ ] Slide deck: stage-by-stage story, results table, honest caveats
- [ ] Prepare Q&A answers

---

## 👥 Team & Work Split

| Person | Role | Owns | Deliverable target |
|--------|------|-------|--------------------|
| **Member 1** | Capture & kiosk UI | Webcam capture/ring buffer, face detection and quality gates, kiosk screens, latency display (`src/capture/`, `src/detect/`, `src/quality/`, `ui/`) | Reliable capture flow; clear ALLOW / REQUEST VERIFICATION / DENY result with reason and elapsed time |
| **Member 2** | PAD, identity & decision | PAD baseline and burst aggregation, face matching, thresholds, spoof veto, tri-state rules (`src/pad/`, `src/identity/`, `src/decision/`, `src/challenge/`, `models/`) | End-to-end decision contract; at least two tested spoof types; uncertain cases escalate and spoof evidence always blocks ALLOW |
| **Member 3** | Integration, evaluation & demo | FastAPI/WebSocket integration, AWS S3/CloudWatch where sandbox permits, evaluation harness, metrics, results and demo (`src/api/`, `aws/`, `eval/`, `docs/`, `demo/`) | Working integrated flow; per-scenario results and confidence intervals; p50/p95/p99 latency; rehearsed demo and local fallback |

### Shared integration contract

Agree on this interface before parallel implementation. A request carries a session ID and a short sequence of frames (or a capture reference); the response contains `decision`, `reason_code`, `liveness_score`, `identity_match`, `identity_score`, `confidence`, and `latency_ms`. The UI and evaluation harness should be able to use a mock response until the real model pipeline is ready.

### Delivery gates

1. **Walking skeleton:** camera → detector → single-frame PAD baseline → identity check → decision → UI, with latency logged. This is the working fallback and the baseline for comparison.
2. **B-lite:** add 8–10-frame burst aggregation and uncertainty routing; keep identity and PAD parallel where practical, with a hard spoof veto.
3. **Evidence:** freeze thresholds on development data, then evaluate genuine users and at least two spoof species on a subject/device-disjoint test set. Report APCER per attack species, BPCER, genuine and attack escalation rates, false accepts/rejects, and Clopper–Pearson intervals. Aggregate by presentation/session, not individual frames.
4. **Performance and demo:** measure end-to-end time from the agreed trigger through displayed decision; target ≤2 seconds and report percentiles. Keep the app local-first; AWS telemetry/dashboard is secondary and must not enter the decision path.

Each member owns their listed directories and commits small, reviewable changes. Member 3 coordinates shared interfaces and integration. All three jointly run the final evaluation and rehearse the demo. If the deadline is shorter than ten days, preserve the walking skeleton and evaluation first; treat the nonce challenge, AWS dashboard, and mask testing as stretch goals.

---

## 🔬 Spoof Attack Coverage

| Attack Type | In Scope | Planned Demo |
|-------------|----------|--------------|
| Printed photo (flat) | ✅ | ✅ |
| Phone/screen photo | ✅ | ✅ |
| Screen/video replay | ✅ | ✅ |
| Paper mask | ✅ | ✅ (stretch) |
| 3D silicone/resin mask | ⚠️ Out of model scope | Acknowledge limitation |
| Camera-stream injection / virtual camera | ⚠️ Architecture scope | Mention in threat model |
| Deepfake stream | ⚠️ Architecture scope | Mention in threat model |

> **3D masks note:** An RGB-only camera cannot reliably detect high-quality silicone or resin masks. We will demonstrate printed/paper masks and explicitly state this limit — the poster example says "Mask (3D / Printed)" so printed masks are the primary target.

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Inference runtime | ONNX Runtime (warm sessions) |
| Capture | OpenCV |
| API | FastAPI (Python) |
| Frontend | HTML/JS or Gradio |
| Cloud | AWS S3, CloudWatch |
| PAD backbone | MobileNetV2 / CDCNet (research-only license) |
| Face recognition | ArcFace / FaceNet (ONNX) |
| Evaluation | Python, scikit-learn, Clopper-Pearson |

---

## 📚 Key References

| # | Paper | Relevance |
|---|-------|-----------|
| 7 | Yu et al., *CDC Networks*, CVPR 2020 | 0.2% ACER on OULU-NPU P1 — research reference (non-commercial) |
| 14 | Kim et al., *ECLIPS*, CVPRW 2024 | CLIP ViT backbone, Monte-Carlo dropout, video-level metric aggregation |
| 15 | Zhang et al., *CelebA-Spoof*, ECCV 2020 | 625K images, 10K+ subjects, 43 attributes — evaluation dataset |
| 25 | Lorenz et al., *Foundation Models for Face PAD*, IJCB 2026 | Cross-dataset not reliable — honest benchmark caveat |
| extra | Li et al., *OT-Guided Adaptation*, CVPR 2025 | 19.17% avg HTER improvement via kiosk-camera adaptation |

---

## ⚠️ Honest Caveats

- Published 99.4% / 99.2% / 0.2% FAR / 0.6% FRR figures are **reference targets**, not guaranteed results.
- Cross-dataset error rates are far higher (single-to-double digit HTER range).
- 50 attack presentations showing 0 failures only bounds APCER ≤ 6% at 95% confidence — not 0.2%.
- We will report Clopper-Pearson intervals and state what the system cannot do.

---

*Research brief: HID Hackathon 2026 — "Can You Spot a Spoof?" · Prepared 14 Nov 2026*
