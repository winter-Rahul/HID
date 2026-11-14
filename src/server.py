"""
FastAPI Server for HID Fortified-PAD Kiosk with Context & Offline Fail-Safe
"""
import os
import cv2
import time
from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from src.pipeline import KioskPipeline

app = FastAPI(title="HID Liveness & Context-Aware Kiosk API")

# Initialize global pipeline
pipeline = KioskPipeline()


def generate_frames():
    """Generates MJPEG stream with real-time detection overlay."""
    while True:
        frame = pipeline.camera.get_latest_frame()
        if frame is None:
            time.sleep(0.03)
            continue

        disp_frame = frame.copy()
        det = pipeline.detector.detect(frame)
        if det is not None:
            x, y, w, h = det["bbox"]
            color = (0, 255, 120) if pipeline.offline_mgr.is_online() else (0, 180, 255)
            cv2.rectangle(disp_frame, (x, y), (x + w, y + h), color, 2)
            label = f"Face {det['score']:.2f}" + (" [OFFLINE]" if not pipeline.offline_mgr.is_online() else "")
            cv2.putText(
                disp_frame,
                label,
                (x, max(20, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                color,
                2,
            )

        ret, buffer = cv2.imencode(".jpg", disp_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not ret:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
        )
        time.sleep(0.03)


@app.get("/api/stream")
def video_stream():
    """MJPEG live camera stream."""
    return StreamingResponse(
        generate_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


class AuthRequest(BaseModel):
    scenario: Optional[str] = "genuine_live"
    simulated_hour: Optional[int] = None


@app.post("/api/authenticate")
def authenticate(req: AuthRequest):
    """
    Triggers the full burst authentication pipeline (< 2s).
    Returns contract: { decision, reason_code, liveness_score, identity_match, schedule_allowed, online_mode, latency_ms }
    """
    result = pipeline.process_burst(scenario=req.scenario, simulated_hour=req.simulated_hour)
    return result


@app.get("/health")
@app.post("/health")
def health(offline: Optional[bool] = Query(None)):
    """Health check endpoint that can toggle online/offline mode for demo."""
    if offline is not None:
        pipeline.offline_mgr.set_online_status(not offline)
    status = pipeline.offline_mgr.get_queue_status()
    status["status"] = "healthy"
    return status


@app.post("/api/toggle_offline")
def toggle_offline(enable_offline: bool = Form(...)):
    """Toggles online / offline fail-safe state."""
    pipeline.offline_mgr.set_online_status(not enable_offline)
    return pipeline.offline_mgr.get_queue_status()


@app.post("/api/enroll")
def enroll(name: str = Form(...)):
    """Enrolls current face in camera as an authorized user."""
    if not name or len(name.strip()) == 0:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    res = pipeline.enroll_user(name.strip())
    return res


@app.get("/api/users")
def get_users():
    """Returns list of enrolled users."""
    users = pipeline.recognizer.list_users()
    schedules = pipeline.schedule_mgr.schedules
    return {"users": users, "schedules": schedules}


@app.delete("/api/users/{name}")
def delete_user(name: str):
    """Removes an enrolled user."""
    success = pipeline.recognizer.remove_user(name)
    return {"success": success}


@app.get("/api/metrics")
def get_metrics():
    """Returns per-scenario ISO/IEC 30107-3 metrics and latency percentiles."""
    metrics = pipeline.telemetry.get_summary()
    queue_stat = pipeline.offline_mgr.get_queue_status()
    return {"metrics": metrics, "offline_status": queue_stat}


@app.post("/api/reset_metrics")
def reset_metrics():
    """Resets telemetry history."""
    pipeline.telemetry = pipeline.telemetry.__class__()
    pipeline.telemetry.save()
    return {"status": "reset"}


# Mount static files for UI
os.makedirs("ui", exist_ok=True)
app.mount("/static", StaticFiles(directory="ui"), name="static")


@app.get("/")
def index():
    return FileResponse("ui/index.html")
