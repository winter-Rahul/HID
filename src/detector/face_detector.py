"""
YuNet Face Detector & Quality Assessment Module
Supports:
1. Primary Face Identification (largest, most central face in interaction zone)
2. Robust Anti-Tailgating (only flags genuine secondary intruder faces, filters distant background people)
3. 5-point facial landmark alignment
4. Quality assessment (blur, size, brightness)
"""
import os
import cv2
import threading
import numpy as np
from typing import Optional, Tuple, Dict, Any, List

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class FaceDetector:
    _lock = threading.Lock()

    def __init__(
        self,
        model_path: str = "models/face_detection_yunet_2023mar.onnx",
        input_size: Tuple[int, int] = (640, 480),
        score_threshold: float = 0.75,
        nms_threshold: float = 0.3,
        top_k: int = 10,
    ):
        self.model_path = model_path
        self.input_size = input_size
        self.score_threshold = score_threshold
        self.nms_threshold = nms_threshold
        self.top_k = top_k

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Detector model not found at {model_path}")

        self.detector = cv2.FaceDetectorYN.create(
            model=model_path,
            config="",
            input_size=input_size,
            score_threshold=score_threshold,
            nms_threshold=nms_threshold,
            top_k=top_k,
        )

    def detect(self, frame: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Detects faces in frame. Thread-safe for concurrent MJPEG streaming and authentication calls.
        """
        if frame is None or frame.size == 0:
            return None

        h, w = frame.shape[:2]
        with self._lock:
            if (w, h) != self.input_size:
                self.input_size = (w, h)
                self.detector.setInputSize((w, h))

            _, faces = self.detector.detect(frame)

        if faces is None or len(faces) == 0:
            return None

        # Sort faces by bounding box area (largest first -> primary foreground user)
        valid_faces = []
        for face in faces:
            bbox = face[0:4].astype(int)
            fw, fh = bbox[2], bbox[3]
            area = fw * fh
            score = float(face[14])
            if area > 1200 and score >= self.score_threshold:  # minimum valid face size
                valid_faces.append((area, face))

        if not valid_faces:
            return None

        valid_faces.sort(key=lambda x: x[0], reverse=True)
        primary_area, primary_face = valid_faces[0]

        # Count how many intrusive faces exist in the kiosk zone
        # A secondary face is a tailgater if its area is >= 40% of the primary face
        intrusive_faces = 1
        for area, face in valid_faces[1:]:
            if area >= primary_area * 0.40:
                intrusive_faces += 1

        bbox = primary_face[0:4].astype(int)
        landmarks = primary_face[4:14].reshape(5, 2).astype(float)
        score = float(primary_face[14])

        x, y, fw, fh = bbox
        x2 = min(w, x + fw)
        y2 = min(h, y + fh)
        x = max(0, x)
        y = max(0, y)
        fw = x2 - x
        fh = y2 - y

        if fw <= 10 or fh <= 10:
            return None

        face_crop = frame[y : y + fh, x : x + fw]

        # Quality metrics
        gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
        brightness = float(np.mean(gray_crop))

        all_bboxes = []
        for _, f in valid_faces:
            fb = f[0:4].astype(int)
            all_bboxes.append([int(fb[0]), int(fb[1]), int(fb[2]), int(fb[3])])

        return {
            "n_faces": intrusive_faces,
            "total_detected_raw": len(faces),
            "all_bboxes": all_bboxes,
            "bbox": [int(x), int(y), int(fw), int(fh)],
            "raw_face": primary_face,
            "landmarks": landmarks.tolist(),
            "score": score,
            "crop": face_crop,
            "laplacian_var": laplacian_var,
            "brightness": brightness,
        }
