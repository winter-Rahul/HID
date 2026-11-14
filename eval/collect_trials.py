"""Interactively collect operator-labelled camera trials without saving images."""
import argparse
import json
import time
from pathlib import Path
import numpy as np


def report(records):
    lines = ["# Kiosk evaluation", "", "Operator-labelled end-to-end trials; not a PAD certification.", "", "| Scenario | Trials | Allow | Step-up | Deny | p50 ms | p95 ms |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for scenario in ("genuine_live", "printed_photo", "screen_replay"):
        trials = [r for r in records if r["scenario"] == scenario]
        if not trials:
            continue
        latencies = [r["latency_ms"] for r in trials]
        counts = [sum(r["decision"] == decision for r in trials) for decision in ("ALLOW", "STEP_UP_VERIFICATION", "DENY")]
        lines.append(f"| {scenario} | {len(trials)} | {counts[0]} | {counts[1]} | {counts[2]} | {np.percentile(latencies, 50):.1f} | {np.percentile(latencies, 95):.1f} |")
    lines.extend(["", "Small samples and repeated presentations are not proof of accuracy. The ALLOW count is an end-to-end result, not PAD-only APCER."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="data/eval_trials.jsonl")
    parser.add_argument("--report", help="Write a report to this path when the session ends")
    args = parser.parse_args()
    from src.pipeline import KioskPipeline
    kiosk = KioskPipeline()
    # A separate trial file is the source of truth; do not rewrite normal telemetry.
    kiosk.telemetry.record_decision = lambda *args, **kwargs: None
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if kiosk.model_status != "ready" or not kiosk.offline_mgr.is_online():
            raise RuntimeError("Models must be ready and kiosk must be in online mode")
        while True:
            label = input("Presentation [g]enuine, [p]rint, [s]creen, [q]uit: ").strip().lower()
            if label == "q":
                break
            scenarios = {"g": "genuine_live", "p": "printed_photo", "s": "screen_replay"}
            if label not in scenarios:
                continue
            input("Position the labelled presentation, keep it still, and press Enter to scan: ")
            # Let the ring buffer replace any previous presentation before scoring.
            time.sleep(1.1)
            result = kiosk.process_burst(scenario=scenarios[label])
            if result.get("reason_code") == "NO_CAMERA_FRAME":
                print("Camera unavailable; no trial recorded.")
                continue
            record = {"scenario": scenarios[label], "decision": result["decision"], "reason_code": result["reason_code"], "latency_ms": result["latency_ms"], "liveness_score": result.get("liveness_score"), "identity_score": result.get("identity_score")}
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, allow_nan=False) + "\n")
            print(f"{record['decision']} ({record['reason_code']}), {record['latency_ms']} ms")
    finally:
        kiosk.camera.stop()
    if args.report and path.exists():
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        Path(args.report).write_text(report(records), encoding="utf-8")


if __name__ == "__main__":
    main()
