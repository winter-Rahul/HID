"""
Unit and Integration Tests for HID Kiosk Decision Engine & Pipelines
Includes tests for:
1. Hard Spoof Veto
2. Uncertainty-Aware Routing (STEP_UP_VERIFICATION)
3. Context-Aware Access Control (Schedule Violation DENY)
4. Offline Fail-Safe Mode (Zero Fail-Open Guarantee)
"""
import pytest
import numpy as np
from src.decision.decision_engine import DecisionEngine
from src.context.schedule import ScheduleManager
from src.offline.fail_safe import OfflineFailSafe


def test_hard_spoof_veto():
    """Verify that a presentation attack cue ALWAYS results in DENY, even if identity matches perfectly."""
    engine = DecisionEngine()
    
    evidence = {
        "n_faces": 1,
        "bbox": [50, 50, 150, 150],
        "laplacian_var": 120.0,
        "brightness": 110.0,
        "p_live": 0.15,               # MiniFASNet flagged spoof
        "strong_attack_cue": True,     # Screen moire detected
        "attack_reason": "Screen replay moiré pattern detected",
        "id_matched": True,            # SFace matched enrolled CEO!
        "id_name": "Executive Officer",
        "id_score": 0.98,
        "uncertainty": 0.02,
        "online_mode": True,
        "error": False,
    }
    
    result = engine.decide(evidence)
    assert result["decision"] == "DENY"
    assert result["allow"] is False
    assert result["reason_code"] == "SPOOF_DETECTED"


def test_uncertainty_routes_to_step_up():
    """Verify that high temporal variance or borderline liveness routes to STEP_UP_VERIFICATION."""
    engine = DecisionEngine()
    
    evidence = {
        "n_faces": 1,
        "bbox": [50, 50, 150, 150],
        "laplacian_var": 95.0,
        "brightness": 90.0,
        "p_live": 0.58,               # Borderline between T_SPOOF (0.4) and T_LIVE (0.7)
        "strong_attack_cue": False,
        "id_matched": True,
        "id_name": "Alice",
        "id_score": 0.85,
        "uncertainty": 0.09,          # Exceeds U_MAX (0.08)
        "online_mode": True,
        "error": False,
    }
    
    result = engine.decide(evidence)
    assert result["decision"] == "STEP_UP_VERIFICATION"
    assert result["allow"] is False
    assert result["reason_code"] == "UNCERTAIN_LIVENESS"


def test_context_schedule_violation(tmp_path):
    """Surprise Challenge 01: Verify that a live, recognized person OUTSIDE their schedule is DENIED."""
    engine = DecisionEngine()
    sched_mgr = ScheduleManager(str(tmp_path / "schedules.json"))
    sched_mgr.set_user_schedule("Alex Morgan", 8, 18, ["Mon", "Tue", "Wed", "Thu", "Fri"])
    
    # Check access for standard business hours employee at 03:00 AM
    sched_res = sched_mgr.check_access("Alex Morgan", simulated_hour=3)
    assert sched_res["allowed"] is False
    
    evidence = {
        "n_faces": 1,
        "bbox": [50, 50, 150, 150],
        "laplacian_var": 120.0,
        "brightness": 110.0,
        "p_live": 0.96,               # Live person
        "strong_attack_cue": False,
        "id_matched": True,            # Correct identity
        "id_name": "Alex Morgan",
        "id_score": 0.88,
        "uncertainty": 0.02,
        "schedule_check": sched_res,  # Schedule violation
        "online_mode": True,
        "error": False,
    }
    
    result = engine.decide(evidence)
    assert result["decision"] == "DENY"
    assert result["allow"] is False
    assert result["reason_code"] == "SCHEDULE_VIOLATION"


def test_multiple_faces_trigger_step_up():
    """Verify that multiple faces detected in view routes to STEP_UP_VERIFICATION (anti-tailgating)."""
    engine = DecisionEngine()
    
    evidence = {
        "n_faces": 2,                 # Tailgater / multiple people
        "bbox": [50, 50, 150, 150],
        "laplacian_var": 120.0,
        "brightness": 110.0,
        "p_live": 0.95,
        "strong_attack_cue": False,
        "id_matched": True,
        "id_name": "Alex Morgan",
        "id_score": 0.88,
        "uncertainty": 0.02,
        "online_mode": True,
        "error": False,
    }
    
    result = engine.decide(evidence)
    assert result["decision"] == "STEP_UP_VERIFICATION"
    assert result["allow"] is False
    assert result["reason_code"] == "MULTIPLE_FACES"


def test_offline_fail_safe_zero_fail_open(tmp_path):
    """Surprise Challenge 02: System never fails open when disconnected; requires step-up verification."""
    engine = DecisionEngine()
    offline_mgr = OfflineFailSafe(str(tmp_path / "queue.json"))
    offline_mgr.set_online_status(False) # Disconnect
    
    evidence = {
        "n_faces": 1,
        "bbox": [50, 50, 150, 150],
        "laplacian_var": 120.0,
        "brightness": 110.0,
        "p_live": 0.95,
        "strong_attack_cue": False,
        "id_matched": True,
        "id_name": "Contractor",
        "id_score": 0.48,             # Sub-threshold for offline emergency bypass
        "uncertainty": 0.02,
        "schedule_check": {"allowed": True, "emergency_override": False},
        "online_mode": False,          # OFFLINE
        "error": False,
    }
    
    result = engine.decide(evidence)
    # Must NOT be ALLOW (Zero Fail-Open)
    assert result["decision"] == "STEP_UP_VERIFICATION"
    assert result["allow"] is False
    assert result["reason_code"] == "OFFLINE_VERIFICATION_REQUIRED"
