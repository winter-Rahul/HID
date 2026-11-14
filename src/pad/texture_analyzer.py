"""
Fourier & Multi-Cue Texture Frequency Analyzer for Presentation Attack Detection
Calibrated for real-world kiosks to avoid false positives on eyeglasses, reflections, and natural skin variations.
"""
import cv2
import numpy as np
from typing import Dict, Any


class TextureAnalyzer:
    def __init__(self, moire_peak_threshold: float = 3.2):
        self.moire_peak_threshold = moire_peak_threshold

    def analyze(self, face_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Analyzes a face crop for presentation attack artifacts.
        Distinguishes between genuine screen replays and natural artifacts like eyeglasses reflections.
        """
        h, w = face_bgr.shape[:2]
        if h < 20 or w < 20:
            return {"texture_live_score": 0.85, "moire_detected": False, "glare_detected": False}

        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

        # 1. Fourier / Moiré analysis
        resized_gray = cv2.resize(gray, (128, 128)).astype(np.float32)
        dft = cv2.dft(resized_gray, flags=cv2.DFT_COMPLEX_OUTPUT)
        dft_shift = np.fft.fftshift(dft)
        magnitude = cv2.magnitude(dft_shift[:, :, 0], dft_shift[:, :, 1])
        mag_spectrum = np.log(magnitude + 1.0)

        # High-frequency band analysis (outer ring of spectrum)
        center_y, center_x = 64, 64
        y, x = np.ogrid[:128, :128]
        dist_from_center = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)

        # Concentrated high-frequency harmonic mask (screens show sharp periodic lattice spikes)
        hf_mask = (dist_from_center >= 40) & (dist_from_center <= 60)
        hf_energy = np.mean(mag_spectrum[hf_mask])

        # High-frequency peak ratio: digital screens have very high localized harmonic spikes
        hf_max = np.max(mag_spectrum[hf_mask]) if np.any(hf_mask) else 0.0
        peak_ratio = (hf_max / (hf_energy + 1e-6)) if hf_energy > 0 else 1.0
        # Calibrated threshold (screen moiré lattice typically spikes > 3.2)
        moire_detected = peak_ratio > self.moire_peak_threshold

        # 2. Specular Glare / Screen Surface Reflection
        # Screen replays and glossy laminates reflect across a massive portion of the surface (> 8%)
        # Eyeglass reflections are localized and should not trigger a false alarm
        hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]
        s_channel = hsv[:, :, 1]
        glare_pixels = np.sum((v_channel > 250) & (s_channel < 25))
        total_pixels = h * w
        glare_ratio = glare_pixels / float(total_pixels)
        glare_detected = glare_ratio > 0.085  # Only flag large-area surface glare (screens/glossy prints)

        # 3. Color Gamut Variance (YCrCb)
        ycrcb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2YCrCb)
        cr = ycrcb[:, :, 1]
        cb = ycrcb[:, :, 2]
        cr_std = float(np.std(cr))
        cb_std = float(np.std(cb))

        score = 0.90
        if moire_detected:
            score -= 0.50
        if glare_detected:
            score -= 0.35
        if cr_std < 2.5 and cb_std < 2.5:  # unnaturally flat / monochrome print
            score -= 0.35

        texture_live_score = float(np.clip(score, 0.05, 0.99))

        return {
            "texture_live_score": round(texture_live_score, 4),
            "moire_detected": moire_detected,
            "peak_ratio": round(float(peak_ratio), 3),
            "glare_detected": glare_detected,
            "glare_ratio": round(float(glare_ratio), 4),
            "skin_variance": round(float(cr_std + cb_std), 2),
        }
