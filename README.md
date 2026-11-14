# HID Hackathon 2026 — "Can You Spot a Spoof?"

> **Liveness Detection + Context-Aware Face Authentication Kiosk**
> Status: 🟡 In Progress · Research complete · Building now

---

## 🎯 Challenge Summary

Build a **kiosk prototype** that runs the full pipeline:

```
Capture → Liveness Check → Face Authentication → Context Check → Decision
                                                                    |
                                              ALLOW / STEP-UP VERIFICATION / DENY
```

**Core Requirements:**
- Complete pipeline in **<= 2 seconds**
- Demonstrate against **at least 2 spoof types** (print, screen replay, video, paper mask)
- Show **per-scenario results**: accuracy, false acceptance/rejection, decision time
- Handle **low-confidence cases** with STEP-UP VERIFICATION (recapture, OTP, or simple action)

**Surprise Challenge — Secure Access Beyond Liveness:**

> *"Recognising a live person is no longer enough for automatic entry"*

### 01 Context-Aware Access Control
- Liveness alone does NOT grant access
- **Cross-reference the biometric match with the campus access schedule**
- Three outcomes: **ALLOW** / **STEP-UP VERIFICATION** / **DENY**

### 02 Offline Fail-Safe Mode
- If the kiosk loses connection to the central server — **the system must NEVER fail open**
- Switch to a safe local decision flow with **offline fallback verification**
- Cache only the **minimum temporary data** needed for auditing — no raw biometrics
- **Auto-sync** all offline decisions once connectivity returns

---

## 🏗 Architecture — "Architecture B-lite" + Surprise Layer

```
┌─────────────┐   ┌────────────────────────┐   ┌────────────────────────┐
│  Webcam      │──▶│  PAD Ensemble          │──▶│  Decision Engine       │
│  (RGB only)  │   │  (8-10 frames, 0.7s)   │   │  3-state output        │
└─────────────┘   └────────────────────────┘   └────────────┬───────────┘
                           │                                 │
                           ▼                                 ▼
                  ┌─────────────────┐          ┌────────────────────────┐
                  │ Face Recognition│          │ Context-Aware Layer    │
                  │ (ArcFace ONNX)  │──────────▶ Cross-ref schedule DB  │
                  └─────────────────┘          │ (online / offline)     │
                                               └────────────┬───────────┘
                                                            │
                               ┌────────────────────────────┤
                               │                            │
                    ┌──────────▼──────┐          ┌──────────▼──────────┐
                    │  ONLINE MODE    │          │  OFFLINE FAIL-SAFE  │
                    │  Sync to server │          │  Local-only decision │
                    │  Full audit log │          │  No raw biometrics   │
                    └─────────────────┘          │  Queue sync on reconnect│
                                                 └─────────────────────┘
```

**Key design decisions:**

| Property | Choice | Reason |
|----------|--------|--------|
| Sensor | RGB-only webcam | 2 s budget; no IR/depth hardware |
| PAD strategy | Passive ensemble over short burst | No active challenge needed; faster |
| Temporal logic | 8-10 frames ~0.7 s, aggregate scores | Avoids single-frame false spikes |
| Decision states | ALLOW / STEP-UP VERIFICATION / DENY | Covers uncertainty + surprise challenge |
| Hard veto | Spoof flag blocks identity even on match | Security-first pipeline |
| Context check | Cross-ref identity with access schedule | Surprise challenge requirement |
| Offline mode | Local fallback, never fail open | Surprise challenge requirement |
| Inference | ONNX Runtime (warm sessions) | Low latency, kiosk-friendly, works offline |

---

## 💡 Innovations We Can Defend

1. **Uncertainty-aware tri-state decisions** — selective-risk protocol: what fraction of genuine users get escalated per APCER level.
2. **Nonce-based screen-light challenge** — used *only* on the STEP-UP path; a pre-recorded replay cannot answer it.
3. **Context-Aware Access Control** — identity match alone is not sufficient; campus schedule gates the final ALLOW.
4. **Offline Fail-Safe** — system degrades safely, never fails open, queues decisions for sync.

---

## 📊 Judging Criteria & Our Strategy

| Criterion | Weight | What Wins | Our Plan |
|-----------|--------|-----------|----------|
| Problem-solution fit | 25% | Show we solve *spoofing*, not just recognition | Liveness is vetoing; identity cross-checked with schedule; never fail open |
| Innovation | 20% | A defensible, measurable idea over a baseline | Tri-state + context-aware access + offline fail-safe |
| Technical implementation | 25% | Feasible, modular, uses APIs/frameworks, scalable | ONNX Runtime kiosk, FastAPI, offline queue, reproducible eval scripts |
| Functionality & usability | 15% | A working live demo | Webcam UI with latency, reason codes, online/offline status indicator |
| Presentation | 15% | Clear to non-technical judges, strong Q&A | Per-scenario table, honest caveats, surprise challenge addressed directly |

---

## 📐 Metrics We Report

| Metric | Definition | Note |
|--------|-----------|------|
| **APCER** (per attack species *s*) | Attack presentations classified as bona fide / all presentations of *s* | Report **worst species**, not the average |
| **BPCER** | Genuine presentations classified as attack / all genuine | |
| **ACER** | (APCER + BPCER) / 2 | Summary only; hides worst attack |
| **EER** | Operating point where APCER = BPCER | Honest only if threshold set on dev set |
| **Genuine escalation rate** | Genuine users routed to STEP-UP VERIFICATION | Friction but not a false reject |
| **Attack escalation rate** | Attacks routed to STEP-UP VERIFICATION | Safe, not an acceptance |
| **Offline fail-open rate** | Decisions allowed during offline mode without local verification | Must be 0% |

> **Stats discipline:** Clopper-Pearson 95% CIs, bootstrap over *subjects* not frames, never tune thresholds on the test set.

---

## 🗂 Project Structure

```
HID/
├── README.md
├── models/
│   ├── pad/                 # MiniFASNet / Silent-Face ONNX
│   └── face/                # ArcFace ONNX
├── src/
│   ├── capture/             # Webcam burst capture (8-10 frames)
│   ├── liveness/            # PAD ensemble inference
│   ├── identity/            # Face embedding + cosine match
│   ├── decision/            # 3-state decision engine + hard veto
│   ├── context/             # [NEW] Access schedule cross-reference
│   ├── offline/             # [NEW] Offline fail-safe mode + sync queue
│   └── api/                 # FastAPI /verify endpoint + pipeline.py
├── ui/                      # Kiosk webcam frontend (Gradio / HTML)
│                            #   includes online/offline status banner
├── eval/                    # metrics.py + results.csv
└── docs/
    └── slides/              # Presentation deck
```

---

## 🗓 Implementation Plan — 5 Hours, 3 People

> **Event window: 11:15 AM - 4:17 PM** | Hard freeze: **3:45 PM** | Last 30 min = demo + pitch

---

### Hour 1 — Setup & Skeleton `11:15 - 12:15`
> **First 15 min all together:** clone repo, install deps, divide tasks. **Agree on the shared response contract:**
> `{ decision, reason_code, liveness_score, identity_match, schedule_allowed, online_mode, latency_ms }`

| Who | Task |
|-----|------|
| **P1** | Python env + OpenCV + ONNX Runtime; write `src/capture/` — 8-10 frame burst from webcam |
| **P2** | Download MiniFASNet / Silent-Face ONNX; write `src/liveness/` returning `{live: bool, score: float}` |
| **P3** | Download ArcFace ONNX; write `src/identity/` embedding + cosine match; stub `src/context/` with a hardcoded schedule dict `{person_id: [allowed_hours]}` |

**Exit:** Each module runs stand-alone on a test image. Contract struct agreed.

---

### Hour 2 — Core Pipeline + Context Layer `12:15 - 1:15`

| Who | Task |
|-----|------|
| **P1** | Integrate capture → liveness: aggregate burst frame scores, return final `{live, score}` |
| **P2** | Write `src/decision/` — 3-state engine: **hard veto if spoofed → DENY**; if live, check `schedule_allowed` → ALLOW or STEP-UP VERIFICATION; write `src/offline/` stub that flags `online=False` and queues decision locally |
| **P3** | Complete `src/context/` schedule checker (time-of-day + person_id lookup); glue everything in `pipeline.py`; expose `FastAPI POST /verify`; add `/health` that toggles online/offline mode for demo |

**Exit:** `POST /verify` returns a decision JSON in < 2 s. Toggling `/health?offline=true` triggers offline fallback (never ALLOW without local verification).

---

### Hour 3 — UI + Spoof Attack Tests `1:15 - 2:15`

| Who | Task |
|-----|------|
| **P1** | Kiosk UI: live webcam feed, decision badge (green/orange/red), confidence, latency, **online/offline status banner** |
| **P2** | Run attacks: **printed photo** + **screen/video replay**. Also test: **schedule-denied identity** (valid face, outside allowed hours → DENY). Log all to `eval/results.csv` |
| **P3** | Write `eval/metrics.py` — APCER/BPCER per attack type, Clopper-Pearson 95% CI; also log offline-mode decisions and confirm zero fail-opens |

**Exit:** UI works end-to-end; >= 2 spoof types + 1 schedule-denial tested and logged.

---

### Hour 4 — Results Table + Slides `2:15 - 3:15`

| Who | Task |
|-----|------|
| **P1** | Demo hardening: catch all exceptions; fallback to Arch A (single frame) if burst fails; **if offline and no local cache match → always DENY, never ALLOW** |
| **P2** | Fill results table (per-scenario APCER / BPCER / decision-time / escalation rate); add offline mode test result row; write honest caveats |
| **P3** | Slide deck (6 slides): Problem → Surprise Challenge → Architecture → Innovation → Results table → Live demo + Limitations |

**Exit:** Slides done, demo runs cleanly 3x in a row (once in offline mode).

---

### Hour 5 — Buffer + Presentation Prep `3:15 - 4:17`

- [ ] Final dry-run: demo in **online mode** then toggle to **offline mode** mid-demo
- [ ] Rehearse 2-min pitch + anticipated Q&A (see Q&A prep below)
- [ ] Push final code, tag `v1.0-hackathon`
- [ ] **Hard freeze at 3:45 PM — zero new features after this**

---

## 👥 Team & Work Split (3 People)

| Person | Role | Owns throughout |
|--------|------|-----------------|
| **P1** | Capture & UI Lead | Webcam burst, frame aggregation, kiosk UI with online/offline banner, demo hardening (`src/capture/`, `ui/`) |
| **P2** | Liveness, Decision & Offline Lead | PAD inference, 3-state engine, hard spoof veto, context-aware schedule check, offline fail-safe, attack testing, results table (`src/liveness/`, `src/decision/`, `src/offline/`, `eval/`) |
| **P3** | Pipeline, Context & Slides Lead | FastAPI glue, identity matching, schedule checker, `pipeline.py`, slide deck (`src/api/`, `src/identity/`, `src/context/`, `docs/`) |

> **Sync:** 5-min standup at the top of each hour — blocked? swap tasks immediately.
> **P1 owns the live demo** in the final 30 min — only they touch the running app.

---

## 🔬 Spoof Attack Coverage

| Attack Type | In Scope | Planned Demo |
|-------------|----------|--------------|
| Printed photo (flat) | Yes | Yes |
| Phone/screen photo | Yes | Yes |
| Screen/video replay | Yes | Yes |
| Schedule-denied valid identity | Yes (surprise challenge) | Yes |
| Offline mode — forced DENY | Yes (surprise challenge) | Yes |
| Paper mask | Yes | Stretch |
| 3D silicone/resin mask | Out of model scope | Acknowledge limitation |
| Deepfake / virtual camera | Architecture scope | Mention in threat model |

---

## 🛡 Offline Fail-Safe Rules (Never Break These)

1. **Never fail open** — no connectivity = no ALLOW without local match
2. **No raw biometrics cached** — store only hashed embeddings + decision + timestamp
3. **Queue all offline decisions** — auto-sync to server when connectivity returns
4. **Degrade gracefully** — UI shows offline banner; STEP-UP VERIFICATION still available locally

---

## 🔧 Tech Stack

| Layer | Technology |
|-------|-----------|
| Inference runtime | ONNX Runtime (warm sessions, works offline) |
| Capture | OpenCV |
| API | FastAPI (Python) |
| Frontend | Gradio or HTML/JS |
| PAD model | MiniFASNet / Silent-Face (ONNX, open weights) |
| Face recognition | ArcFace (ONNX) |
| Context / Schedule | JSON / SQLite (offline-safe) |
| Offline queue | SQLite local store + sync on reconnect |
| Evaluation | Python, scipy (Clopper-Pearson) |

---

## 🎤 Q&A Prep

| Likely question | Our answer |
|-----------------|------------|
| What if a spoofer is also scheduled? | Spoof veto fires first — DENY always wins over schedule |
| What happens offline? | Local embedding match only, never ALLOW without it; all offline decisions queued and synced |
| What can't your system detect? | High-quality 3D silicone masks; deepfake video injection (architecture-level, not model-level) |
| Why three states? | Uncertainty is real — honest escalation beats silent false accepts |
| Are your accuracy numbers reliable? | We report Clopper-Pearson CIs; 50 attacks can only bound APCER <= 6% at 95% confidence |

---

## 📚 Key References

| # | Paper | Relevance |
|---|-------|-----------|
| 7 | Yu et al., *CDC Networks*, CVPR 2020 | 0.2% ACER on OULU-NPU P1 — research reference |
| 14 | Kim et al., *ECLIPS*, CVPRW 2024 | CLIP ViT backbone, video-level metric aggregation |
| 15 | Zhang et al., *CelebA-Spoof*, ECCV 2020 | 625K images, 10K+ subjects — evaluation dataset |
| 25 | Lorenz et al., *Foundation Models for Face PAD*, IJCB 2026 | Cross-dataset not reliable — honest benchmark caveat |

---

## Honest Caveats

- Published 99.4% / 99.2% / 0.2% FAR / 0.6% FRR figures are **reference targets**, not guaranteed results.
- Cross-dataset error rates are far higher (single to double digit HTER range).
- 50 attack presentations showing 0 failures only bounds APCER <= 6% at 95% confidence.
- We report confidence intervals and explicitly state what the system cannot do.

---

*HID Hackathon 2026 — "Can You Spot a Spoof?" + Surprise Challenge: "Secure Access Beyond Liveness" | 14 Nov 2026*
