"""
YuNet Face Detector & Quality Assessment Module
"""
import os
import cv2
import numpy as np
from typing import Optional, Tuple, Dict, Any

# Ensure Intel OpenMP does not crash
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class FaceDetector:
    def __init__(
        self,
        model_path: str = "models/face_detection_yunet_2023mar.onnx",
        input_size: Tuple[int, int] = (640, 480),
        score_threshold: float = 0.7,
        nms_threshold: float = 0.3,
        top_k: int = 1,
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
        Detects primary face in frame.
        Returns dictionary with bbox, landmarks, score, and quality metrics.
        """
        h, w = frame.shape[:2]
        if (w, h) != self.input_size:
            self.input_size = (w, h)
            self.detector.setInputSize((w, h))

        _, faces = self.detector.detect(frame)

        if faces is None or len(faces) == 0:
            return None

        # Take primary face (highest score)
        face = faces[0]
        bbox = face[0:4].astype(int)  # [x, y, w, h]
        landmarks = face[4:14].reshape(5, 2).astype(float)
        score = float(face[14])

        x, y, fw, fh = bbox
        x = max(0, x)
        y = max(0, y)
        fw = min(fw, w - x)
        fh = min(fh, h - y)

        if fw <= 10 or fh <= 10:
            return None

        face_crop = frame[y : y + fh, x : x + fw]

        # Quality metrics
        gray_crop = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray_crop, cv2.CV_64F).var())
        brightness = float(np.mean(gray_crop))

        return {
            "bbox": [int(x), int(y), int(fw), int(fh)],
            "raw_face": face,  # 15-dim numpy array for SFace alignment
            "landmarks": landmarks.tolist(),
            "score": score,
            "crop": face_crop,
            "laplacian_var": laplacian_var,
            "brightness": brightness,
        }
