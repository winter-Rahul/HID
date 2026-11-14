"""
End-to-End Kiosk Authentication Pipeline with Context & Offline Fail-Safe
Integrates: Capture -> Detector -> PAD -> SFace Identity -> Schedule Context -> Offline Gate -> Decision -> Telemetry
Contract: { decision, reason_code, liveness_score, identity_match, schedule_allowed, online_mode, latency_ms }
"""
import time
import numpy as np
import yaml
from typing import Dict, Any, Optional

from src.detector.face_detector import FaceDetector, framing_issue
from src.identity.face_recognizer import FaceRecognizer
from src.pad.liveness_detector import LivenessDetector
from src.decision.decision_engine import DecisionEngine
from src.context.schedule import ScheduleManager
from src.offline.fail_safe import OfflineFailSafe
from src.capture.camera import CameraStream
from src.telemetry.logger import TelemetryLogger


def mean_embedding(features):
    """Average consistent face embeddings and normalize the resulting template."""
    values = np.asarray(features, dtype=np.float32)
    if values.ndim != 2 or len(values) < 3 or not np.isfinite(values).all():
        raise ValueError("Invalid face embeddings")
    mean = values.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if not np.isfinite(norm) or norm <= 1e-8:
        raise ValueError("Invalid mean face embedding")
    return mean / norm


class KioskPipeline:
    def __init__(
        self,
        camera: Optional[CameraStream] = None,
        config_path: str = "configs/pipeline.yaml",
    ):
        print("[KioskPipeline] Initializing models and engines...")
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        detector, identity, pad, quality = (config[k] for k in ("detector", "identity", "pad", "quality"))
        self.detector = FaceDetector(model_path=detector["model_path"], score_threshold=detector["score_threshold"], nms_threshold=detector["nms_threshold"], top_k=detector["top_k"])
        self.recognizer = FaceRecognizer(model_path=identity["model_path"], storage_file=config["storage"]["enrolled_faces_file"], cosine_threshold_high=identity["cosine_threshold_high"], cosine_threshold_low=identity["cosine_threshold_low"], margin_min=identity["margin_min"])
        self.pad = LivenessDetector(model_path=pad["model_path"], t_spoof=pad["t_spoof"], t_live=pad["t_live"], u_max_variance=pad["u_max_variance"])
        self.decision_engine = DecisionEngine(t_spoof=pad["t_spoof"], t_live=pad["t_live"], u_max_variance=pad["u_max_variance"], min_laplacian_var=quality["min_laplacian_var"], min_brightness=quality["min_brightness"], max_brightness=quality["max_brightness"], min_face_size=max(quality["min_face_width"], quality["min_face_height"]))
        self.schedule_mgr = ScheduleManager()
        self.offline_mgr = OfflineFailSafe()
        self.telemetry = TelemetryLogger()

        self.camera = camera if camera is not None else CameraStream(camera_index=config["kiosk"]["camera_index"], width=config["kiosk"]["frame_width"], height=config["kiosk"]["frame_height"])
        self.burst_size = config["capture"]["burst_size"]
        self.model_status = "warming"
        try:
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            self.detector.detect(frame)
            bbox = [200, 120, 200, 220]
            self.pad.predict_frame(frame, bbox)
            face = np.array([200, 120, 200, 220, 250, 200, 350, 200, 300, 240, 260, 290, 340, 290, .99], dtype=np.float32)
            feature = self.recognizer.extract_feature(frame, face)
            if not np.isfinite(feature).all():
                raise ValueError("Recognition model produced invalid output")
            self.model_status = "ready"
        except Exception as exc:
            self.model_status = "error"
            print(f"[KioskPipeline] Model warm-up failed: {exc}")
        print("[KioskPipeline] Pipeline ready with Context & Offline Fail-Safe.")

    def enroll_user(self, name: str, start_hour: int = 0, end_hour: int = 24, days=None) -> Dict[str, Any]:
        """Captures a clean face from the webcam and enrolls the user."""
        if name in self.recognizer.list_users():
            return {"success": False, "message": "Name is already enrolled"}
        burst = self.camera.get_burst(self.burst_size)
        checks = []
        enrollment_features = []
        for _, sample in burst:
            face = self.detector.detect(sample)
            if face is None or face.get("n_faces", 1) != 1:
                return {"success": False, "message": "A single face must be visible throughout enrollment"}
            hint = framing_issue(face, sample.shape)
            if hint:
                return {"success": False, "message": hint}
            if (face["laplacian_var"] < self.decision_engine.min_laplacian_var or
                    not self.decision_engine.min_brightness <= face["brightness"] <= self.decision_engine.max_brightness or
                    min(face["bbox"][2:4]) < self.decision_engine.min_face_size):
                return {"success": False, "message": "Enrollment frame quality is insufficient; adjust lighting and hold still"}
            checks.append(self.pad.predict_frame(sample, face["bbox"]))
            enrollment_features.append(self.recognizer.extract_feature(sample, face["raw_face"]).flatten())
        if len(checks) < 3:
            return {"success": False, "message": "Not enough frames for enrollment"}
        live = self.pad.aggregate_burst(checks)
        if live["strong_attack_cue"] or live["p_live"] < self.decision_engine.t_live or live["uncertainty"] > self.decision_engine.u_max_variance:
            return {"success": False, "message": "Liveness could not be verified for enrollment"}
        frame = self.camera.get_latest_frame()
        if frame is None:
            return {"success": False, "message": "Failed to capture frame from camera"}

        det = self.detector.detect(frame)
        if det is None:
            return {"success": False, "message": "No face detected for enrollment"}

        if det.get("n_faces", 1) != 1:
            return {"success": False, "message": "Only one person may be present during enrollment"}

        if det["laplacian_var"] < 35.0:
            return {"success": False, "message": "Face image is too blurry. Hold still."}

        feature = self.recognizer.extract_feature(frame, det["raw_face"])
        if any(float(np.dot(feature.flatten(), candidate)) < self.recognizer.cosine_threshold_high for candidate in enrollment_features):
            return {"success": False, "message": "Face changed during enrollment"}
        try:
            template = mean_embedding(enrollment_features)
        except ValueError:
            return {"success": False, "message": "Invalid enrollment features; please retry"}
        probe_match = self.recognizer.match(feature)
        template_match = self.recognizer.match(template)
        if any(
            result.get("score", 0.0) >= self.recognizer.cosine_threshold_high
            for result in (probe_match, template_match)
        ):
            return {"success": False, "message": "Face may already be enrolled; verify identity before retrying"}

        success = self.recognizer.enroll_feature(name, template)
        # Register a default weekday business-hours schedule for new users.
        if success and name not in self.schedule_mgr.schedules:
            self.schedule_mgr.set_user_schedule(name, start_hour=start_hour, end_hour=end_hour, days=days or ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        return {"success": success, "name": name, "message": f"Successfully enrolled {name} with campus access" if success else "Enrollment failed"}

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
                result = {
                    "decision": "DENY",
                    "reason_code": "NO_CAMERA_FRAME",
                    "message": "Camera stream unavailable",
                    "liveness_score": None,
                    "identity_match": False,
                    "schedule_allowed": False,
                    "online_mode": online_mode,
                    "confidence": 0.0,
                    "latency_ms": total_lat,
                }
                if not online_mode:
                    self.offline_mgr.queue_offline_decision("DENY", None, result["reason_code"], total_lat)
                self.telemetry.record_decision(scenario, "DENY", total_lat, result)
                return result
        timing_breakdown["capture_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # 2. Per-frame detection & PAD
        t0 = time.monotonic()
        pad_results = []
        best_face_det = None
        best_quality = -1.0
        best_frame = None
        max_faces = 0
        detected_frames = []

        for ts, frame in burst:
            det = self.detector.detect(frame)
            if det is None:
                continue
            max_faces = max(max_faces, det.get("n_faces", 1))
            detected_frames.append((frame, det))

            qual = det["laplacian_var"]
            if qual > best_quality:
                best_quality = qual
                best_face_det = det
                best_frame = frame

            pad_res = self.pad.predict_frame(frame, det["bbox"])
            pad_results.append(pad_res)

        timing_breakdown["detect_pad_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # If no face was detected across burst
        if best_face_det is None or best_frame is None or not pad_results:
            total_lat = round((time.monotonic() - t_start) * 1000, 1)
            ev = {"n_faces": 0, "error": False, "online_mode": online_mode}
            dec = self.decision_engine.decide(ev)
            dec["liveness_score"] = None
            dec["identity_match"] = False
            dec["schedule_allowed"] = False
            dec["online_mode"] = online_mode
            dec["latency_ms"] = total_lat
            dec["timings"] = timing_breakdown
            self.telemetry.record_decision(scenario, dec["decision"], total_lat, dec)
            if not online_mode:
                self.offline_mgr.queue_offline_decision(dec["decision"], None, dec["reason_code"], total_lat)
            return dec

        # Do not attempt recognition or offer a PIN while another qualifying
        # face was visible anywhere in the burst.
        if max_faces > 1:
            total_lat = round((time.monotonic() - t_start) * 1000, 1)
            dec = self.decision_engine.decide({"n_faces": max_faces, "online_mode": online_mode})
            dec.update({"liveness_score": None, "identity_match": False, "schedule_allowed": False,
                        "online_mode": online_mode, "latency_ms": total_lat, "timings": timing_breakdown})
            if not online_mode:
                self.offline_mgr.queue_offline_decision(dec["decision"], None, dec["reason_code"], total_lat)
            self.telemetry.record_decision(scenario, dec["decision"], total_lat, dec)
            return dec

        t0 = time.monotonic()
        pad_agg = self.pad.aggregate_burst(pad_results)
        timing_breakdown["pad_agg_ms"] = round((time.monotonic() - t0) * 1000, 1)
        hint = framing_issue(best_face_det, best_frame.shape)
        if hint:
            total_lat = round((time.monotonic() - t_start) * 1000, 1)
            spoof = pad_agg["strong_attack_cue"] or pad_agg["p_live"] <= self.decision_engine.t_spoof
            dec = {"decision": "DENY" if spoof else "STEP_UP_VERIFICATION", "reason_code": "SPOOF_DETECTED" if spoof else "FACE_POSITION",
                   "message": "Presentation attack detected." if spoof else hint, "confidence": None, "liveness_score": pad_agg["p_live"],
                   "identity_match": False, "schedule_allowed": False, "online_mode": online_mode,
                   "latency_ms": total_lat, "timings": timing_breakdown}
            if not online_mode:
                self.offline_mgr.queue_offline_decision(dec["decision"], None, dec["reason_code"], total_lat)
            self.telemetry.record_decision(scenario, dec["decision"], total_lat, dec)
            return dec

        # 4. Identity matching (on best quality aligned frame)
        t0 = time.monotonic()
        feat = self.recognizer.extract_feature(best_frame, best_face_det["raw_face"])
        consistent = len(detected_frames) >= 3 and len(detected_frames) == len(burst)
        features = []
        if not np.isfinite(feat).all() or float(np.linalg.norm(feat)) <= 1e-8:
            return {"decision": "STEP_UP_VERIFICATION", "reason_code": "INVALID_IDENTITY_FEATURE", "message": "Identity measurement unavailable; please retry.", "liveness_score": pad_agg["p_live"], "identity_score": None, "identity_match": False, "schedule_allowed": False, "online_mode": online_mode, "confidence": None, "latency_ms": round((time.monotonic() - t_start) * 1000, 1), "timings": timing_breakdown}
        if consistent:
            probe = feat.flatten()
            for frame, det in detected_frames:
                candidate = self.recognizer.extract_feature(frame, det["raw_face"]).flatten()
                if not np.isfinite(candidate).all() or float(np.dot(probe, candidate)) < self.recognizer.cosine_threshold_high:
                    consistent = False
                    break
                # All frames must match; exclude low-quality frames only from
                # the mean, never from the cross-frame identity check.
                if (det["laplacian_var"] < self.decision_engine.min_laplacian_var or
                        not self.decision_engine.min_brightness <= det["brightness"] <= self.decision_engine.max_brightness or
                        min(det["bbox"][2:4]) < self.decision_engine.min_face_size):
                    continue
                features.append(candidate)
        if consistent:
            try:
                feat = mean_embedding(features)
            except ValueError:
                consistent = False
        id_res = self.recognizer.match(feat)
        timing_breakdown["identity_ms"] = round((time.monotonic() - t0) * 1000, 1)

        # 5. Context schedule check
        sched_check = {"allowed": False, "reason": "No match to schedule"}
        if id_res["name"]:
            sched_check = self.schedule_mgr.check_access(id_res["name"], simulated_hour=simulated_hour)

        # 6. Evidence fusion
        n_faces = max_faces
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
        if decision_result["decision"] == "ALLOW" and not consistent:
            decision_result = {"decision": "STEP_UP_VERIFICATION", "reason_code": "INCONSISTENT_BURST", "message": "Insufficient consistent face frames. Please retry.", "confidence": None}
        timing_breakdown["decision_ms"] = round((time.monotonic() - t0) * 1000, 1)

        total_latency_ms = round((time.monotonic() - t_start) * 1000, 1)
        if total_latency_ms > 2000 and decision_result["decision"] == "ALLOW":
            decision_result = self.decision_engine.decide({"timed_out": True})
            decision_result["confidence"] = None

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
