# HID Hackathon 2026 — "Can You Spot a Spoof?"

## Running the prototype

Choose the CPU setup for a broadly compatible install, or the optional NVIDIA setup below for CUDA-backed MiniFASNet inference. Use a separate virtual environment for each because `onnxruntime` and `onnxruntime-gpu` install the same Python module.

### CPU setup (default)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python run_kiosk.py
```

Open `http://127.0.0.1:8000` in a browser. A webcam and the three ONNX files in `models/` are required. The launcher loads `HID_ADMIN_TOKEN` from the project root's `.env` file; an existing environment variable takes precedence. If the token is unset, the launcher creates or reuses a random token in the ignored file `data/.admin_token`; retrieve it locally when the browser prompts for it. Run the automated tests with `python -m pytest -q`. On macOS or Linux, activate the environment with `source .venv/bin/activate` instead.

This is a research prototype, not an access-control product. Management operations and labelled demo scenarios require a token; normal scans do not. Keep the token secret and bind the service to loopback. The optional enrollment PIN is stored as a salted PBKDF2 hash and can complete eligible short-lived step-up challenges. Rate limits and challenges are held in memory and reset on restart; this is not a production authentication system. The PAD implementation uses raw BGR pixels and class 1 as live, following the upstream Silent-Face implementation; the exporter model card describes different preprocessing and labels for the same model hash. Validate with live, printed and screen presentations before a demo. The two-second target, attack detection rates, and reliability have not been established by automated tests. The offline switch is manual. On reconnect, a local mock receiver durably acknowledges queued events in a local SQLite database; it is not a remote central server or a connectivity detector. Biometric templates are stored locally in plaintext JSON. Template and telemetry files have been removed from the current Git index, but real data remains in earlier public repository history; removing current files does not purge that history. Do not use real users' biometrics without addressing these gaps. Core model paths, camera settings and decision thresholds are read from `configs/pipeline.yaml`; not every field in that file is implemented.

The UI's end-to-end allow and deny rates are not PAD-only APCER or BPCER. Existing telemetry and the checked-in report may contain inconsistent or historical demo data and should not be presented as validated results. Record new consented, labelled trials under a documented protocol before reporting performance.

Ordinary scans and the print/screen demo labels do not require the management token. Labels are supplied by the browser and are not independently verified; unauthenticated clients can therefore influence demo telemetry. Enrollment, user management, metrics, offline control and the simulated schedule-violation clock still require the token.

The UI displays a liveness score and face-embedding cosine similarity separately; neither is a calibrated probability. New enrollments and consistent authentication bursts use normalized mean embeddings. This changes similarity scores even though the matching thresholds are unchanged, so validate false matches and non-matches on held-out participants before deployment. The camera requests 640×480 and a face at least 80 pixels across; verify camera support and latency on the target device. Use even frontal lighting and enroll in conditions similar to normal use. Existing single-frame templates must be evaluated or re-enrolled with consent.

Capture asks the camera to enable automatic white balance when supported and gives positioning, lighting, distance and blur guidance. Framing checks use face-box and landmark heuristics and may need adjustment for the target camera. Spoof and identity inference still use the camera's captured frames; the app cannot add physical lighting or recover detail absent from a distant or blurred image. These adjustments do not guarantee a similarity score above any particular value.

### Optional NVIDIA GPU setup (Windows x64)

The GPU requirements use ONNX Runtime 1.32.0 with its CUDA 13 and cuDNN 9 runtime packages. A compatible NVIDIA driver and CUDA-capable GPU are required. Create a separate environment and launch the kiosk from that environment:

```powershell
python -m venv .venv-gpu
.\.venv-gpu\Scripts\Activate.ps1
python -m pip install -r requirements-gpu.txt
python run_kiosk.py
```

The GPU wheel's CUDA/cuDNN extras install the matching runtime libraries; a separate CUDA Toolkit install is not needed for this setup. Confirm the driver and ONNX Runtime providers with:

```powershell
nvidia-smi
python -c "import onnxruntime as ort; print(ort.get_available_providers())"
```

The provider list should include `CUDAExecutionProvider`. At startup, the kiosk also logs the active providers for MiniFASNet. The detector tries CUDA first and falls back to CPU if CUDA is unavailable or fails to initialize.

CUDA currently accelerates **MiniFASNet liveness inference only**. YuNet face detection, SFace recognition, texture analysis, camera capture, and the rest of the API still run on CPU; this setup does not enable CUDA for those stages. Because MiniFASNet is a small 80×80 model, GPU transfer and launch overhead may outweigh its compute savings. On one RTX 3050 check, a 100-inference microbenchmark measured 1.89 ms median on CPU and 3.35 ms on CUDA. This is PAD-only timing, not a full kiosk benchmark, and performance varies by machine. Measure end-to-end scan latency before choosing the GPU environment for a demo.

If the log shows CPU only, confirm that `.venv-gpu` is activated, `onnxruntime-gpu` is installed there, and `CUDAExecutionProvider` appears in the provider list. The default CPU setup remains available independently.

The checked-in PAD model has SHA-256 `d7b3cd9ba8a7ceb13baa8c4720902e27ca3112eff52f926c08804af6b6eecc7b`. The [original Silent-Face NumPy conversion](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/blob/master/src/data_io/functional.py) returns unscaled float pixels, and its [test script](https://github.com/minivision-ai/Silent-Face-Anti-Spoofing/blob/master/test.py) identifies class 1 as real. The [ONNX exporter model card](https://huggingface.co/garciafido/minifasnet-v2-anti-spoofing-onnx) claims normalized pixels and class 0 for the same export. These sources conflict; current behavior follows the original code, but no independent output-equivalence or physical-attack accuracy claim has been established. Invalid model logits cause inference to fail rather than produce an access decision.

> **Liveness Detection + Context-Aware Face Authentication Kiosk**
> Status: 🟡 In Progress · Research complete · Building now

The challenge requirements, architecture, proposed innovations, implementation plan, and Q&A below describe the original goals and demo plan. They are not a statement that all features have been implemented or validated. Remote synchronization and a nonce challenge are not implemented. The admin-only schedule-violation scenario simulates 03:00; select the weekday schedule during enrollment to demonstrate it. Existing schedules are not changed.

To collect operator-labelled trials without saving images, run `python -m eval.collect_trials --report docs/results.md`, then present genuine, printed-photo and phone-screen samples as prompted. The report is preliminary end-to-end data, not a PAD certification; do not overwrite the report until actual trials are available.

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
2. **Proposed nonce-based screen-light challenge** — intended for the STEP-UP path; not implemented or validated.
3. **Context-Aware Access Control** — identity match alone is not sufficient; campus schedule gates the final ALLOW.
4. **Offline Fail-Safe** — the prototype queues offline decisions locally; a real sync integration and its reliability still need validation.

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
| Inference runtime | ONNX Runtime CPU by default; optional CUDA execution provider for MiniFASNet only |
| Capture | OpenCV |
| API | FastAPI (Python) |
| Frontend | Gradio or HTML/JS |
| PAD model | MiniFASNet / Silent-Face (ONNX, open weights) |
| Face recognition | ArcFace (ONNX) |
| Context / Schedule | JSON / SQLite (offline-safe) |
| Offline queue | Local JSON queue with a local mock SQLite receiver; remote synchronization not implemented |
| Evaluation | Python, scipy (Clopper-Pearson) |

---

## 🎤 Q&A Prep

| Likely question | Our answer |
|-----------------|------------|
| What if a spoofer is also scheduled? | Spoof veto fires first — DENY always wins over schedule |
| What happens offline? | The demo queues decisions locally; returning to online mode syncs them to a local mock receiver, not a remote server. |
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
