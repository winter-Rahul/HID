"""
FastAPI Server for HID Fortified-PAD Kiosk with Context & Offline Fail-Safe
Bulletproof Stream & Concurrency Protection
"""
import os
import cv2
import time
import secrets
import threading
import logging
from fastapi import Depends, FastAPI, Form, Header, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.offline.mock_central import MockCentral
from src.step_up import StepUp
from typing import Optional

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from src.pipeline import KioskPipeline

app = FastAPI(title="HID Liveness & Context-Aware Kiosk API")


class MockSyncRequest(BaseModel):
    events: list[dict]


@app.post("/api/mock-sync")
def mock_sync(request: MockSyncRequest, x_admin_token: Optional[str] = Header(None)):
    require_admin(x_admin_token)
    try:
        return {"acknowledged": MockCentral().accept(request.events)}
    except (KeyError, TypeError):
        raise HTTPException(status_code=400, detail="Each event requires a sync_id")

# Initialize global pipeline
pipeline = KioskPipeline()
pipeline_lock = threading.RLock()
step_up = StepUp()


def require_admin(x_admin_token: Optional[str] = Header(None)):
    """Require an explicitly configured management credential."""
    expected = os.environ.get("HID_ADMIN_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Management access is not configured")
    if not x_admin_token or not secrets.compare_digest(x_admin_token.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid management credential")


def generate_frames():
    """
    Generates high-performance MJPEG stream.
    Bulletproof: Wrapped in error boundary so camera stream NEVER dies or goes blank.
    """
    reported_error = False
    while True:
        try:
            frame = pipeline.camera.get_latest_frame()
            if frame is None:
                time.sleep(0.04)
                continue

            disp_frame = frame.copy()

            # If recent detection bbox exists, draw it smoothly
            bbox = getattr(pipeline, "last_active_bbox", None)
            if bbox is not None and time.monotonic() - getattr(pipeline, "last_overlay_time", 0) < 3:
                x, y, w, h = bbox
                color = (0, 255, 120) if pipeline.offline_mgr.is_online() else (0, 180, 255)
                cv2.rectangle(disp_frame, (x, y), (x + w, y + h), color, 2)
                matched = getattr(pipeline, "last_matched_name", "Live Face")
                cv2.putText(
                    disp_frame,
                    f"{matched}",
                    (x, max(24, y - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                )

            ret, buffer = cv2.imencode(".jpg", disp_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ret:
                time.sleep(0.02)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            reported_error = False
            time.sleep(0.03)

        except Exception:
            if not reported_error:
                logging.getLogger(__name__).exception("Camera stream failed")
                reported_error = True
            time.sleep(0.05)
            continue


@app.get("/api/stream")
def video_stream():
    """MJPEG live camera stream with fail-safe keepalive."""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )


class AuthRequest(BaseModel):
    scenario: Optional[str] = "genuine_live"


@app.post("/api/authenticate")
def authenticate(req: AuthRequest, x_admin_token: Optional[str] = Header(None)):
    """
    Triggers the full burst authentication pipeline (< 2s).
    Thread-safe and updates persistent tracking state.
    """
    simulated = req.scenario in ("schedule_violation", "schedule_denied")
    if req.scenario not in (None, "genuine_live", "printed_photo", "screen_replay", "video_replay", "paper_mask", "unknown_person", "schedule_violation", "schedule_denied"):
        raise HTTPException(status_code=400, detail="Invalid scenario")
    if simulated:
        require_admin(x_admin_token)
    if getattr(pipeline, "model_status", "ready") != "ready":
        raise HTTPException(status_code=503, detail="Models are not ready")
    with pipeline_lock:
        result = pipeline.process_burst(scenario=req.scenario, simulated_hour=3) if simulated else pipeline.process_burst(scenario=req.scenario)
        if (not simulated and result.get("decision") == "STEP_UP_VERIFICATION" and
                result.get("reason_code") in ("OFFLINE_VERIFICATION_REQUIRED", "BORDERLINE_IDENTITY", "UNCERTAIN_LIVENESS") and
                result.get("matched_user") and result.get("schedule_allowed")):
            challenge = step_up.issue(result["matched_user"])
            if challenge:
                result["step_up_challenge"] = challenge
        pipeline.last_active_bbox = result.get("bbox") if result.get("decision") == "ALLOW" else None
        pipeline.last_matched_name = result.get("matched_user") if pipeline.last_active_bbox else None
        pipeline.last_overlay_time = time.monotonic()
    return result


class StepUpRequest(BaseModel):
    challenge: str
    pin: str


@app.post("/api/step-up")
def verify_step_up(request: StepUpRequest):
    with pipeline_lock:
        name = step_up.verify(request.challenge, request.pin)
        if not name or name not in pipeline.recognizer.list_users() or not pipeline.schedule_mgr.check_access(name).get("allowed", False):
            return {"decision": "DENY", "reason_code": "STEP_UP_FAILED", "message": "Verification failed or expired."}
        if not pipeline.offline_mgr.is_online():
            pipeline.offline_mgr.queue_offline_decision("ALLOW", name, "STEP_UP_VERIFIED", 0)
        return {"decision": "ALLOW", "reason_code": "STEP_UP_VERIFIED", "message": "Secondary credential verified.", "matched_user": name}


@app.get("/health")
def health():
    """Report local status without changing operational state."""
    status = pipeline.offline_mgr.get_queue_status()
    status["model_status"] = getattr(pipeline, "model_status", "unknown")
    status["status"] = "healthy" if status["model_status"] == "ready" else "not_ready"
    return status


@app.post("/api/toggle_offline", dependencies=[Depends(require_admin)])
def toggle_offline(enable_offline: bool = Form(...)):
    """Toggles online / offline fail-safe state."""
    with pipeline_lock:
        pipeline.offline_mgr.set_online_status(not enable_offline)
        return pipeline.offline_mgr.get_queue_status()


@app.post("/api/enroll", dependencies=[Depends(require_admin)])
def enroll(name: str = Form(...), start_hour: int = Form(0), end_hour: int = Form(24), days: str = Form("Mon,Tue,Wed,Thu,Fri,Sat,Sun"), pin: str = Form("")):
    """Enrolls current face in camera as an authorized user."""
    if not name or len(name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    selected_days = days.split(",")
    if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 24 or start_hour == end_hour or not selected_days or any(day not in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun") for day in selected_days):
        raise HTTPException(status_code=400, detail="Invalid access schedule")
    if pin and not (pin.isascii() and pin.isdigit() and 6 <= len(pin) <= 12):
        raise HTTPException(status_code=400, detail="PIN must contain 6 to 12 digits")
    with pipeline_lock:
        res = pipeline.enroll_user(name.strip(), start_hour, end_hour, selected_days)
        if res.get("success") and pin:
            step_up.set_pin(name.strip(), pin)
    return res


@app.get("/api/users", dependencies=[Depends(require_admin)])
def get_users():
    """Returns list of enrolled users."""
    with pipeline_lock:
        users = pipeline.recognizer.list_users()
        schedules = dict(pipeline.schedule_mgr.schedules)
    return {"users": users, "schedules": schedules}


@app.delete("/api/users/{name}", dependencies=[Depends(require_admin)])
def delete_user(name: str):
    """Removes an enrolled user."""
    with pipeline_lock:
        success = pipeline.recognizer.remove_user(name)
        if success:
            pipeline.schedule_mgr.remove_user_schedule(name)
            step_up.remove_pin(name)
    return {"success": success}


@app.post("/api/users/{name}/pin", dependencies=[Depends(require_admin)])
def set_user_pin(name: str, pin: str = Form(...)):
    if not (pin.isascii() and pin.isdigit() and 6 <= len(pin) <= 12):
        raise HTTPException(status_code=400, detail="PIN must contain 6 to 12 digits")
    with pipeline_lock:
        if name not in pipeline.recognizer.list_users():
            raise HTTPException(status_code=404, detail="User not found")
        step_up.set_pin(name, pin)
    return {"success": True}


@app.get("/api/metrics", dependencies=[Depends(require_admin)])
def get_metrics():
    """Returns per-scenario ISO/IEC 30107-3 metrics and latency percentiles."""
    with pipeline_lock:
        metrics = pipeline.telemetry.get_summary()
        queue_stat = pipeline.offline_mgr.get_queue_status()
    return {"metrics": metrics, "offline_status": queue_stat}


@app.post("/api/reset_metrics", dependencies=[Depends(require_admin)])
def reset_metrics():
    """Resets telemetry history."""
    with pipeline_lock:
        pipeline.telemetry.scenarios = {name: {"presentations": 0, "allow": 0, "request": 0, "deny": 0, "latencies_ms": []} for name in pipeline.telemetry.scenarios}
        pipeline.telemetry.history = []
        pipeline.telemetry.save()
    return {"status": "reset"}


# Mount static files for UI
os.makedirs("ui", exist_ok=True)
app.mount("/static", StaticFiles(directory="ui"), name="static")


@app.get("/")
def index():
    return FileResponse("ui/index.html")
