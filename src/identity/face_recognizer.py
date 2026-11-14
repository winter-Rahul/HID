"""
SFace Face Recognition & Enrollment Module
"""
import os
import json
import cv2
import numpy as np
from typing import Optional, List, Dict, Tuple, Any

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class FaceRecognizer:
    def __init__(
        self,
        model_path: str = "models/face_recognition_sface_2021dec.onnx",
        storage_file: str = "data/enrolled_users.json",
        cosine_threshold_high: float = 0.45,
        cosine_threshold_low: float = 0.32,
        margin_min: float = 0.08,
    ):
        self.model_path = model_path
        self.storage_file = storage_file
        self.cosine_threshold_high = cosine_threshold_high
        self.cosine_threshold_low = cosine_threshold_low
        self.margin_min = margin_min

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Recognition model not found at {model_path}")

        self.recognizer = cv2.FaceRecognizerSF.create(model=model_path, config="")
        self.enrolled_users: Dict[str, np.ndarray] = {}
        self._load_enrolled()

    def _load_enrolled(self):
        """Loads enrolled user embeddings from disk."""
        if os.path.exists(self.storage_file):
            try:
                with open(self.storage_file, "r") as f:
                    data = json.load(f)
                    for name, emb_list in data.items():
                        self.enrolled_users[name] = np.array(emb_list, dtype=np.float32)
            except Exception as e:
                print(f"[FaceRecognizer] Error loading {self.storage_file}: {e}")

    def _save_enrolled(self):
        """Saves enrolled user embeddings to disk."""
        os.makedirs(os.path.dirname(self.storage_file), exist_ok=True)
        data = {name: emb.tolist() for name, emb in self.enrolled_users.items()}
        with open(self.storage_file, "w") as f:
            json.dump(data, f, indent=2)

    def extract_feature(self, frame: np.ndarray, raw_face: np.ndarray) -> np.ndarray:
        """
        Aligns the face and extracts a 128-D normalized embedding.
        """
        aligned = self.recognizer.alignCrop(frame, raw_face)
        feature = self.recognizer.feature(aligned)
        # Normalize
        norm = np.linalg.norm(feature)
        if norm > 0:
            feature = feature / norm
        return feature

    def enroll(self, name: str, frame: np.ndarray, raw_face: np.ndarray) -> bool:
        """Enrolls a new user with their extracted embedding."""
        feat = self.extract_feature(frame, raw_face)
        self.enrolled_users[name] = feat
        self._save_enrolled()
        return True

    def remove_user(self, name: str) -> bool:
        if name in self.enrolled_users:
            del self.enrolled_users[name]
            self._save_enrolled()
            return True
        return False

    def list_users(self) -> List[str]:
        return list(self.enrolled_users.keys())

    def match(self, feature: np.ndarray) -> Dict[str, Any]:
        """
        Matches a probe embedding against all enrolled users (1:N matching).
        Returns top match, cosine similarity score, margin, and match status.
        """
        if not self.enrolled_users:
            return {
                "matched": False,
                "name": None,
                "score": 0.0,
                "margin": 0.0,
                "reason": "No enrolled users in database",
            }

        scores: List[Tuple[str, float]] = []
        for name, emb in self.enrolled_users.items():
            # Cosine similarity between normalized 128-D embeddings
            sim = float(np.dot(feature.flatten(), emb.flatten()))
            scores.append((name, sim))

        # Sort descending by score
        scores.sort(key=lambda x: x[1], reverse=True)
        top_name, top_score = scores[0]

        margin = 0.0
        if len(scores) > 1:
            margin = top_score - scores[1][1]
        else:
            margin = top_score

        matched = top_score >= self.cosine_threshold_high and margin >= self.margin_min

        return {
            "matched": matched,
            "name": top_name if top_score >= self.cosine_threshold_low else None,
            "score": round(top_score, 4),
            "margin": round(margin, 4),
            "all_scores": [(n, round(s, 4)) for n, s in scores[:3]],
        }
