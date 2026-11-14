"""
Passive Presentation Attack Detection (PAD) Module
Combines MiniFASNet deep neural network + Fourier/Moiré texture analyzer.
Supports automatic CUDA GPU acceleration when available, with seamless CPU fallback.
"""
import os
import cv2
import numpy as np
import onnxruntime as ort
from typing import List, Dict, Any, Tuple
from src.pad.texture_analyzer import TextureAnalyzer

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"


class LivenessDetector:
    def __init__(
        self,
        model_path: str = "models/minifasnet_v2.onnx",
        t_spoof: float = 0.40,
        t_live: float = 0.65,
        u_max_variance: float = 0.12,
    ):
        self.model_path = model_path
        self.t_spoof = t_spoof
        self.t_live = t_live
        self.u_max_variance = u_max_variance

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"PAD model not found at {model_path}")

        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        available_providers = ort.get_available_providers()
        self.session = None
        if "CUDAExecutionProvider" in available_providers:
            # Newer ORT GPU wheels can load their CUDA/cuDNN DLLs from NVIDIA
            # Python packages. Older/system installs can omit this API or the
            # runtime libraries, so retain a clear CPU fallback.
            preload_dlls = getattr(ort, "preload_dlls", None)
            if preload_dlls is not None:
                try:
                    preload_dlls()
                except (OSError, RuntimeError) as exc:
                    print(f"[LivenessDetector] CUDA runtime preload failed: {exc}")
            try:
                self.session = ort.InferenceSession(
                    model_path,
                    sess_options=opts,
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
                )
            except (OSError, RuntimeError) as exc:
                print(f"[LivenessDetector] CUDA session failed; falling back to CPU: {exc}")

        if self.session is None:
            self.session = ort.InferenceSession(
                model_path, sess_options=opts, providers=["CPUExecutionProvider"]
            )
        self.active_providers = self.session.get_providers()
        self.device_used = (
            "CUDA GPU (with CPU fallback)"
            if "CUDAExecutionProvider" in self.active_providers
            else "CPU"
        )
        self.input_name = self.session.get_inputs()[0].name
        self.texture_analyzer = TextureAnalyzer()
        print(
            f"[LivenessDetector] Loaded MiniFASNet with active providers: "
            f"{self.active_providers} (Running on {self.device_used})"
        )

    def _get_scaled_crop(self, frame: np.ndarray, bbox: List[int], scale: float = 2.7) -> np.ndarray:
        """
        Extracts face crop with specified scale expansion (MiniFASNet uses 2.7x context scale).
        """
        h, w = frame.shape[:2]
        x, y, fw, fh = bbox

        cx = x + fw / 2.0
        cy = y + fh / 2.0

        sw = fw * scale
        sh = fh * scale

        x1 = int(max(0, cx - sw / 2.0))
        y1 = int(max(0, cy - sh / 2.0))
        x2 = int(min(w, cx + sw / 2.0))
        y2 = int(min(h, cy + sh / 2.0))

        crop = frame[y1:y2, x1:x2]
        if crop.size == 0 or crop.shape[0] < 10 or crop.shape[1] < 10:
            return frame[max(0, y) : min(h, y + fh), max(0, x) : min(w, x + fw)]
        return crop

    def predict_frame(self, frame: np.ndarray, bbox: List[int]) -> Dict[str, Any]:
        """
        Runs PAD inference on a single frame.
        Preprocessing: 80x80 BGR resized, float32 raw pixel values.
        """
        scaled_crop = self._get_scaled_crop(frame, bbox, scale=2.7)
        resized = cv2.resize(scaled_crop, (80, 80)).astype(np.float32)

        # Transpose (H, W, C) -> (1, C, H, W)
        blob = np.transpose(resized, (2, 0, 1))[np.newaxis, ...]

        # Model forward pass
        raw_out = self.session.run(None, {self.input_name: blob})[0]  # shape (1, 3)

        # Silent-Face's reference implementation uses unscaled BGR input and
        # treats class 1 as real. The exporter's model card conflicts; see README.
        if raw_out.shape != (1, 3) or not np.isfinite(raw_out).all():
            raise ValueError("PAD model returned invalid logits")
        exp_vals = np.exp(raw_out - np.max(raw_out, axis=1, keepdims=True))
        probs = exp_vals / np.sum(exp_vals, axis=1, keepdims=True)
        p_live_deep = float(probs[0, 1])

        # Texture and moiré frequency analysis
        x, y, width, height = bbox
        face_crop = frame[max(0, y):min(frame.shape[0], y + height), max(0, x):min(frame.shape[1], x + width)]
        tex_res = self.texture_analyzer.analyze(face_crop)
        p_live_texture = tex_res["texture_live_score"]

        # Weighted score: Deep network (80%) + Texture (20%)
        p_live = float(0.80 * p_live_deep + 0.20 * p_live_texture)
        p_live = float(np.clip(p_live, 0.01, 0.99))

        return {
            "p_live": round(p_live, 4),
            "p_live_deep": round(p_live_deep, 4),
            "p_live_texture": round(p_live_texture, 4),
            "moire_detected": tex_res["moire_detected"],
            "glare_detected": tex_res["glare_detected"],
            "peak_ratio": tex_res["peak_ratio"],
        }

    def aggregate_burst(self, frame_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregates predictions over a burst of 8-10 frames.
        Computes median score, variance, and hard attack cues.
        """
        if not frame_results:
            return {
                "p_live": 0.0,
                "uncertainty": 1.0,
                "strong_attack_cue": True,
                "attack_reason": "No frames analyzed",
            }

        scores = [f["p_live"] for f in frame_results]
        deep_scores = [f["p_live_deep"] for f in frame_results]
        median_score = float(np.median(scores))
        median_deep = float(np.median(deep_scores))
        std_dev = float(np.std(scores))

        moire_hits = sum(1 for f in frame_results if f["moire_detected"])
        glare_hits = sum(1 for f in frame_results if f["glare_detected"])

        strong_attack_cue = False
        attack_reason = None

        # Only trigger hard veto if recurring attack patterns or clear model rejection
        if moire_hits >= 4:
            strong_attack_cue = True
            attack_reason = "Screen replay moiré lattice detected"
        elif glare_hits >= 5 and median_deep < 0.50:
            strong_attack_cue = True
            attack_reason = "Screen surface reflection detected"
        elif median_score < self.t_spoof:
            strong_attack_cue = True
            attack_reason = "Presentation attack detected by PAD model"

        return {
            "p_live": round(median_score, 4),
            "p_live_deep": round(median_deep, 4),
            "uncertainty": round(std_dev, 4),
            "all_scores": [round(s, 4) for s in scores],
            "strong_attack_cue": strong_attack_cue,
            "attack_reason": attack_reason,
            "moire_hits": moire_hits,
            "glare_hits": glare_hits,
        }
