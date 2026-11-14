"""
FastAPI Server for HID Fortified-PAD Kiosk with Context & Offline Fail-Safe
Bulletproof Stream & Concurrency Protection
"""
import os
import cv2
import time
import secrets
import threading
from fastapi import Depends, FastAPI, Form, Header, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from src.offline.mock_central import MockCentral
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
            time.sleep(0.03)

        except Exception as e:
            # Bulletproof: Never let the stream die
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
    require_admin(x_admin_token)
    simulated = req.scenario in ("schedule_violation", "schedule_denied")
    with pipeline_lock:
        result = pipeline.process_burst(scenario=req.scenario, simulated_hour=3) if simulated else pipeline.process_burst(scenario=req.scenario)
        pipeline.last_active_bbox = result.get("bbox") if result.get("decision") == "ALLOW" else None
        pipeline.last_matched_name = result.get("matched_user") if pipeline.last_active_bbox else None
        pipeline.last_overlay_time = time.monotonic()
    return result


@app.get("/health")
def health():
    """Report local status without changing operational state."""
    status = pipeline.offline_mgr.get_queue_status()
    status["status"] = "healthy"
    return status


@app.post("/api/toggle_offline", dependencies=[Depends(require_admin)])
def toggle_offline(enable_offline: bool = Form(...)):
    """Toggles online / offline fail-safe state."""
    with pipeline_lock:
        pipeline.offline_mgr.set_online_status(not enable_offline)
        return pipeline.offline_mgr.get_queue_status()


@app.post("/api/enroll", dependencies=[Depends(require_admin)])
def enroll(name: str = Form(...)):
    """Enrolls current face in camera as an authorized user."""
    if not name or len(name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    with pipeline_lock:
        res = pipeline.enroll_user(name.strip())
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
    return {"success": success}


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
