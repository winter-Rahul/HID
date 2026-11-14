"""
Deterministic Tri-State Decision Engine with Context-Aware Access & Offline Fail-Safe
Guarantees:
1. Hard Spoof Veto: A spoof signal immediately vetos identity and denies access.
2. Context-Aware Access: Liveness + Identity is not enough; access schedule gates final ALLOW.
3. Offline Zero-Fail-Open: Under network severance, the system never fails open.
4. Tri-State Outcomes: ALLOW / STEP_UP_VERIFICATION / DENY.
"""
from typing import Dict, Any


class DecisionEngine:
    def __init__(
        self,
        t_spoof: float = 0.40,
        t_live: float = 0.70,
        u_max_variance: float = 0.08,
        min_laplacian_var: float = 40.0,
        min_brightness: float = 35.0,
        max_brightness: float = 245.0,
        min_face_size: int = 80,
    ):
        self.t_spoof = t_spoof
        self.t_live = t_live
        self.u_max_variance = u_max_variance
        self.min_laplacian_var = min_laplacian_var
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness
        self.min_face_size = min_face_size

    def decide(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        """
        Takes fused evidence from capture, detector, PAD, identity, schedule context, and offline state.
        Returns tri-state decision, reason code, display confidence, and telemetry.
        """
        online_mode = evidence.get("online_mode", True)

        # Fail-safe check
        if evidence.get("error") or evidence.get("timed_out"):
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "SYSTEM_TIMEOUT",
                "message": "System could not complete check in time. Please try again.",
                "confidence": 0.0,
                "allow": False,
                "schedule_allowed": False,
            }

        # 0. Face presence and quality gates
        n_faces = evidence.get("n_faces", 0)
        if n_faces == 0:
            return {
                "decision": "DENY",
                "reason_code": "NO_FACE_DETECTED",
                "message": "No face detected in camera field of view.",
                "confidence": 0.0,
                "allow": False,
                "schedule_allowed": False,
            }
        elif n_faces > 1:
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "MULTIPLE_FACES",
                "message": "Multiple faces detected. Please ensure only one person is present.",
                "confidence": 0.0,
                "allow": False,
                "schedule_allowed": False,
            }

        bbox = evidence.get("bbox", [0, 0, 0, 0])
        fw, fh = bbox[2], bbox[3]
        if fw < self.min_face_size or fh < self.min_face_size:
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "FACE_TOO_FAR",
                "message": "Face too far. Please step closer to the kiosk.",
                "confidence": 0.3,
                "allow": False,
                "schedule_allowed": False,
            }

        laplacian_var = evidence.get("laplacian_var", 100.0)
        if laplacian_var < self.min_laplacian_var:
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "IMAGE_BLURRY",
                "message": "Image is blurry. Please hold still for recapture.",
                "confidence": 0.4,
                "allow": False,
                "schedule_allowed": False,
            }

        brightness = evidence.get("brightness", 128.0)
        if brightness < self.min_brightness or brightness > self.max_brightness:
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "POOR_LIGHTING",
                "message": "Poor lighting conditions detected. Adjust ambient lighting.",
                "confidence": 0.4,
                "allow": False,
                "schedule_allowed": False,
            }

        # 1. HARD SPOOF VETO (Decided BEFORE identity is granted)
        p_live = evidence.get("p_live", 0.0)
        strong_attack_cue = evidence.get("strong_attack_cue", False)
        attack_reason = evidence.get("attack_reason", "Presentation attack detected")

        if strong_attack_cue or p_live <= self.t_spoof:
            return {
                "decision": "DENY",
                "reason_code": "SPOOF_DETECTED",
                "message": f"Presentation attack detected: {attack_reason}",
                "confidence": round(1.0 - p_live, 4),
                "allow": False,
                "schedule_allowed": False,
            }

        # 2. LIVENESS UNCERTAINTY ROUTING
        uncertainty = evidence.get("uncertainty", 0.0)
        if p_live < self.t_live or uncertainty > self.u_max_variance:
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "UNCERTAIN_LIVENESS",
                "message": "Liveness confidence is low or unstable. Recapture or secondary factor required.",
                "confidence": round(p_live, 4),
                "allow": False,
                "schedule_allowed": False,
            }

        # 3. IDENTITY VERIFICATION
        id_matched = evidence.get("id_matched", False)
        id_name = evidence.get("id_name", None)
        id_score = evidence.get("id_score", 0.0)

        if not id_name:
            return {
                "decision": "DENY",
                "reason_code": "IDENTITY_NOT_RECOGNIZED",
                "message": "Live person confirmed, but face does not match any enrolled personnel.",
                "confidence": round(p_live, 4),
                "allow": False,
                "schedule_allowed": False,
            }

        if not id_matched:
            return {
                "decision": "STEP_UP_VERIFICATION",
                "reason_code": "BORDERLINE_IDENTITY",
                "message": f"Identity match for {id_name} is borderline. Requesting verification PIN / OTP.",
                "confidence": round(min(p_live, id_score), 4),
                "allow": False,
                "schedule_allowed": False,
            }

        # 4. SURPRISE CHALLENGE 01: CONTEXT-AWARE SCHEDULE ACCESS CHECK
        # "Recognising a live person is no longer enough for automatic entry"
        schedule_check = evidence.get("schedule_check", {"allowed": True, "reason": "Standard Access"})
        schedule_allowed = schedule_check.get("allowed", True)

        if not schedule_allowed:
            return {
                "decision": "DENY",
                "reason_code": "SCHEDULE_VIOLATION",
                "message": f"Context Denial: {id_name} is outside authorized schedule ({schedule_check.get('reason')}).",
                "confidence": round(min(p_live, id_score), 4),
                "name": id_name,
                "allow": False,
                "schedule_allowed": False,
            }

        # 5. SURPRISE CHALLENGE 02: OFFLINE FAIL-SAFE GATE
        # "If the kiosk loses connection to central server — the system must NEVER fail open"
        if not online_mode:
            # Under offline disconnection, grant access ONLY if explicitly verified by local offline model
            # For guest/contractor or non-emergency staff, require STEP_UP_VERIFICATION
            is_emergency = schedule_check.get("emergency_override", False)
            if not is_emergency and id_score < 0.60:
                return {
                    "decision": "STEP_UP_VERIFICATION",
                    "reason_code": "OFFLINE_VERIFICATION_REQUIRED",
                    "message": f"Kiosk is Offline. Secondary credential required for {id_name} (Zero Fail-Open Mode).",
                    "confidence": round(min(p_live, id_score), 4),
                    "name": id_name,
                    "allow": False,
                    "schedule_allowed": True,
                }

        # 6. PASSED ALL CHECKS -> ALLOW
        final_confidence = round(min(p_live, id_score), 4)
        status_suffix = " (Offline Local Mode)" if not online_mode else ""
        return {
            "decision": "ALLOW",
            "reason_code": "ACCESS_GRANTED",
            "message": f"Live person confirmed, schedule authorized, and identity verified as {id_name}{status_suffix}.",
            "confidence": final_confidence,
            "name": id_name,
            "allow": True,
            "schedule_allowed": True,
        }
