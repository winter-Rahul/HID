"""
End-to-End Kiosk Authentication Pipeline with Context & Offline Fail-Safe
Integrates: Capture -> Detector -> PAD -> SFace Identity -> Schedule Context -> Offline Gate -> Decision -> Telemetry
Contract: { decision, reason_code, liveness_score, identity_match, schedule_allowed, online_mode, latency_ms }
"""
import time
import numpy as np
from typing import Dict, Any, Optional

from src.detector.face_detector import FaceDetector
from src.identity.face_recognizer import FaceRecognizer
from src.pad.liveness_detector import LivenessDetector
from src.decision.decision_engine import DecisionEngine
from src.context.schedule import ScheduleManager
from src.offline.fail_safe import OfflineFailSafe
from src.capture.camera import CameraStream
from src.telemetry.logger import TelemetryLogger


class KioskPipeline:
    def __init__(
        self,
        camera: Optional[CameraStream] = None,
        config_path: str = "configs/pipeline.yaml",
    ):
        print("[KioskPipeline] Initializing models and engines...")
        self.detector = FaceDetector(model_path="models/face_detection_yunet_2023mar.onnx")
        self.recognizer = FaceRecognizer(model_path="models/face_recognition_sface_2021dec.onnx")
        self.pad = LivenessDetector(model_path="models/minifasnet_v2.onnx")
        self.decision_engine = DecisionEngine()
        self.schedule_mgr = ScheduleManager()
        self.offline_mgr = OfflineFailSafe()
        self.telemetry = TelemetryLogger()

        self.camera = camera if camera is not None else CameraStream(camera_index=0)
        self.burst_size = 8
        print("[KioskPipeline] Pipeline ready with Context & Offline Fail-Safe.")

    def enroll_user(self, name: str) -> Dict[str, Any]:
        """Captures a clean face from the webcam and enrolls the user."""
        frame = self.camera.get_latest_frame()
        if frame is None:
            return {"success": False, "message": "Failed to capture frame from camera"}

        det = self.detector.detect(frame)
        if det is None:
            return {"success": False, "message": "No face detected for enrollment"}

        if det["laplacian_var"] < 35.0:
            return {"success": False, "message": "Face image is too blurry. Hold still."}

        success = self.recognizer.enroll(name, frame, det["raw_face"])
        # Register standard hackathon & employee schedule (Mon-Sun, 24h)
        self.schedule_mgr.set_user_schedule(name, start_hour=0, end_hour=24, days=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        return {"success": success, "name": name, "message": f"Successfully enrolled {name} with campus access"}

    def process_burst(self, scenario: str = "genuine_live", simulated_hour: Optional[int] = None) -> Dict[str, Any]:
        """
        Executes full end-to-end authentication in <= 2.0s.
        Returns the exact shared response contract.
        """
        t_start = time.monotonic()
        timing_breakdown = {}
        online_mode = self.offline_mgr.is_online()

        # 1. Burst acquisition
        t0 = time.monotonic()
        burst = self.camera.get_burst(self.burst_size)
        if not burst:
            latest = self.camera.get_latest_frame()
            if latest is not None:
                burst = [(time.monotonic(), latest)]
            else:
                total_lat = round((time.monotonic() - t_start) * 1000, 1)
                return {
                    "decision": "DENY",
                    "reason_code": "NO_CAMERA_FRAME",
                    "message": "Camera stream unavailable",
                    "liveness_score": 0.0,
                    "identity_match": False,
                    "schedule_allowed": False,
                    "online_mode": online_mode,
                    "confidence": 0.0,
                    "latency_ms": total_lat,
                }
        timing_breakdown["capture_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # 2. Per-frame detection & PAD
        t0 = time.monotonic()
        pad_results = []
        best_face_det = None
        best_quality = -1.0
        best_frame = None

        for ts, frame in burst:
            det = self.detector.detect(frame)
            if det is None:
                continue

            qual = det["laplacian_var"]
            if qual > best_quality:
                best_quality = qual
                best_face_det = det
                best_frame = frame

            pad_res = self.pad.predict_frame(frame, det["bbox"])
            pad_results.append(pad_res)
            print(
                "[PAD DEBUG]",
                f"deep={pad_res['p_live_deep']:.4f}",
                f"texture={pad_res['p_live_texture']:.4f}",
                f"combined={pad_res['p_live']:.4f}",
                f"moire={pad_res['moire_detected']}",
                f"glare={pad_res['glare_detected']}",
            )

        timing_breakdown["detect_pad_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # If no face was detected across burst
        if best_face_det is None or best_frame is None or not pad_results:
            total_lat = round((time.monotonic() - t_start) * 1000, 1)
            ev = {"n_faces": 0, "error": False, "online_mode": online_mode}
            dec = self.decision_engine.decide(ev)
            dec["liveness_score"] = 0.0
            dec["identity_match"] = False
            dec["schedule_allowed"] = False
            dec["online_mode"] = online_mode
            dec["latency_ms"] = total_lat
            dec["timings"] = timing_breakdown
            self.telemetry.record_decision(scenario, dec["decision"], total_lat, dec)
            if not online_mode:
                self.offline_mgr.queue_offline_decision(dec["decision"], None, dec["reason_code"], total_lat)
            return dec

        # 3. Burst temporal aggregation
        t0 = time.monotonic()
        pad_agg = self.pad.aggregate_burst(pad_results)
        print(
            "[PAD AGGREGATED]",
            f"live={pad_agg['p_live']:.4f}",
            f"deep={pad_agg['p_live_deep']:.4f}",
            f"uncertainty={pad_agg['uncertainty']:.4f}",
            f"attack={pad_agg['strong_attack_cue']}",
            f"reason={pad_agg['attack_reason']}",
        )
        timing_breakdown["pad_agg_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # 4. Identity matching (on best quality aligned frame)
        t0 = time.monotonic()
        feat = self.recognizer.extract_feature(best_frame, best_face_det["raw_face"])
        id_res = self.recognizer.match(feat)
        timing_breakdown["identity_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # 5. Context schedule check
        # Allow simulated hour for demonstration of scenario "schedule_violation"
        test_hour = simulated_hour
        if scenario == "schedule_denied" or scenario == "schedule_violation":
            test_hour = 3  # 03:00 AM (outside normal 08:00 - 18:00 window)

        sched_check = {"allowed": True, "reason": "No match to schedule"}
        if id_res["name"]:
            sched_check = self.schedule_mgr.check_access(id_res["name"], simulated_hour=test_hour)

        # 6. Evidence fusion
        n_faces = best_face_det.get("n_faces", 1)
        evidence = {
            "n_faces": n_faces,
            "bbox": best_face_det["bbox"],
            "laplacian_var": best_face_det["laplacian_var"],
            "brightness": best_face_det["brightness"],
            "p_live": pad_agg["p_live"],
            "uncertainty": pad_agg["uncertainty"],
            "strong_attack_cue": pad_agg["strong_attack_cue"],
            "attack_reason": pad_agg["attack_reason"],
            "id_matched": id_res["matched"],
            "id_name": id_res["name"],
            "id_score": id_res["score"],
            "id_margin": id_res["margin"],
            "schedule_check": sched_check,
            "online_mode": online_mode,
            "error": False,
        }

        # 7. Tri-state decision
        t0 = time.monotonic()
        decision_result = self.decision_engine.decide(evidence)
        timing_breakdown["decision_ms"] = round((time.monotonic() - t0) * 1000, 1)

        total_latency_ms = round((time.monotonic() - t_start) * 1000, 1)

        # Construct shared contract response
        contract_response = {
            "decision": decision_result["decision"],
            "reason_code": decision_result["reason_code"],
            "message": decision_result["message"],
            "liveness_score": pad_agg["p_live"],
            "identity_match": bool(id_res["matched"]),
            "matched_user": id_res["name"],
            "identity_score": id_res["score"],
            "schedule_allowed": bool(sched_check.get("allowed", False)),
            "schedule_details": sched_check.get("reason", ""),
            "online_mode": online_mode,
            "confidence": decision_result["confidence"],
            "latency_ms": total_latency_ms,
            "timings": timing_breakdown,
            "moire_detected": pad_agg["moire_hits"] > 0,
            "bbox": best_face_det["bbox"],
        }

        # Offline queue management
        if not online_mode:
            self.offline_mgr.queue_offline_decision(
                contract_response["decision"],
                contract_response["matched_user"],
                contract_response["reason_code"],
                total_latency_ms,
            )

        # Record to telemetry
        self.telemetry.record_decision(scenario, contract_response["decision"], total_latency_ms, contract_response)

        return contract_response
