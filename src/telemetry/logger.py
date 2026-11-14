"""
Telemetry & Metrics Logger
Tracks per-scenario presentations, decisions, APCER, BPCER, and latency percentiles.
"""
import os
import json
import time
import numpy as np
from typing import Dict, Any, List


class TelemetryLogger:
    def __init__(self, output_file: str = "data/telemetry_metrics.json"):
        self.output_file = output_file
        self.scenarios = {
            "genuine_live": {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []},
            "printed_photo": {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []},
            "screen_replay": {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []},
            "video_replay": {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []},
            "paper_mask": {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []},
            "unknown_person": {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []},
        }
        self.history: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if os.path.exists(self.output_file):
            try:
                with open(self.output_file, "r") as f:
                    data = json.load(f)
                    self.scenarios.update(data.get("scenarios", {}))
                    self.history = data.get("history", [])
            except Exception as e:
                print(f"[TelemetryLogger] Error loading metrics: {e}")

    def save(self):
        os.makedirs(os.path.dirname(self.output_file), exist_ok=True)
        with open(self.output_file, "w") as f:
            json.dump({"scenarios": self.scenarios, "history": self.history[-100:]}, f, indent=2)

    def record_decision(self, scenario: str, decision: str, latency_ms: float, metadata: Dict[str, Any]):
        if scenario not in self.scenarios:
            scenario = "genuine_live"

        sc = self.scenarios[scenario]
        sc["presentations"] += 1
        if decision == "ALLOW":
            sc["allow"] += 1
        elif decision == "REQUEST_VERIFICATION":
            sc["request"] += 1
        elif decision == "DENY":
            sc["deny"] += 1

        sc["latencies_ms"].append(round(latency_ms, 1))

        record = {
            "timestamp": time.time(),
            "scenario": scenario,
            "decision": decision,
            "latency_ms": round(latency_ms, 1),
            "reason_code": metadata.get("reason_code", ""),
            "confidence": metadata.get("confidence", 0.0),
            "p_live": metadata.get("p_live", 0.0),
            "id_score": metadata.get("id_score", 0.0),
        }
        self.history.append(record)
        self.save()

    def get_summary(self) -> Dict[str, Any]:
        """Calculates APCER, BPCER, and latency percentiles per scenario."""
        summary = {}
        for sc_name, sc in self.scenarios.items():
            pres = sc["presentations"]
            if pres == 0:
                summary[sc_name] = {
                    "presentations": 0,
                    "allow": 0,
                    "request": 0,
                    "deny": 0,
                    "apcer": 0.0,
                    "bpcer": 0.0,
                    "p50_latency_ms": 0.0,
                    "p95_latency_ms": 0.0,
                }
                continue

            lats = sc["latencies_ms"]
            p50 = float(np.percentile(lats, 50)) if lats else 0.0
            p95 = float(np.percentile(lats, 95)) if lats else 0.0

            # APCER: for attacks, fraction accepted as live bona fide
            # BPCER: for genuine, fraction rejected as attack
            apcer = (sc["allow"] / float(pres)) if "replay" in sc_name or "photo" in sc_name or "mask" in sc_name else 0.0
            bpcer = (sc["deny"] / float(pres)) if sc_name == "genuine_live" else 0.0

            summary[sc_name] = {
                "presentations": pres,
                "allow": sc["allow"],
                "request": sc["request"],
                "deny": sc["deny"],
                "apcer": round(apcer * 100, 2),
                "bpcer": round(bpcer * 100, 2),
                "p50_latency_ms": round(p50, 1),
                "p95_latency_ms": round(p95, 1),
            }
        return summary
