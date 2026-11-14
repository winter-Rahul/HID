"""
Fourier & Multi-Cue Texture Frequency Analyzer for Presentation Attack Detection
Detects:
1. Screen pixel grid / Moiré patterns via 2D FFT peak energy
2. Print halftone patterns via high-frequency power distribution
3. Specular glare / saturation anomalies common on phone screens
"""
import cv2
import numpy as np
from typing import Dict, Any


class TextureAnalyzer:
    def __init__(self, moire_peak_threshold: float = 0.45):
        self.moire_peak_threshold = moire_peak_threshold

    def analyze(self, face_bgr: np.ndarray) -> Dict[str, Any]:
        """
        Analyzes a face crop for presentation attack artifacts.
        Returns texture score in [0.0, 1.0] where 1.0 is bona fide (live)
        and 0.0 is spoof (screen replay / printed photo).
        """
        h, w = face_bgr.shape[:2]
        if h < 20 or w < 20:
            return {"texture_live_score": 0.5, "moire_detected": False, "glare_detected": False}

        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)

        # 1. Fourier / Moiré analysis
        # Resize to fixed 128x128 for consistent frequency distribution
        resized_gray = cv2.resize(gray, (128, 128)).astype(np.float32)
        
        # 2D FFT
        dft = cv2.dft(resized_gray, flags=cv2.DFT_COMPLEX_OUTPUT)
        dft_shift = np.fft.fftshift(dft)
        magnitude = cv2.magnitude(dft_shift[:, :, 0], dft_shift[:, :, 1])
        mag_spectrum = np.log(magnitude + 1.0)

        # High-frequency band analysis (outer ring of spectrum)
        center_y, center_x = 64, 64
        y, x = np.ogrid[:128, :128]
        dist_from_center = np.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)

        # High-frequency mask (radius 35 to 60)
        hf_mask = (dist_from_center >= 35) & (dist_from_center <= 60)
        hf_energy = np.mean(mag_spectrum[hf_mask])

        # Peak energy ratio: screens have localized sharp harmonic spikes (high max/mean ratio)
        hf_max = np.max(mag_spectrum[hf_mask]) if np.any(hf_mask) else 0.0
        peak_ratio = (hf_max / (hf_energy + 1e-6)) if hf_energy > 0 else 1.0
        moire_detected = peak_ratio > 2.4

        # 2. Specular Glare / Screen Reflection Detection
        # Digital screens and glossy prints have blown-out specular highlights
        hsv = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2HSV)
        v_channel = hsv[:, :, 2]
        s_channel = hsv[:, :, 1]
        glare_pixels = np.sum((v_channel > 248) & (s_channel < 30))
        total_pixels = h * w
        glare_ratio = glare_pixels / float(total_pixels)
        glare_detected = glare_ratio > 0.035

        # 3. Color Gamut Variance (YCrCb)
        # Real human skin has strong natural clustering in Cr and Cb channels
        ycrcb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2YCrCb)
        cr = ycrcb[:, :, 1]
        cb = ycrcb[:, :, 2]
        cr_std = float(np.std(cr))
        cb_std = float(np.std(cb))

        # Combine into texture live score [0, 1]
        score = 0.85
        if moire_detected:
            score -= 0.45
        if glare_detected:
            score -= 0.35
        if cr_std < 3.0 or cb_std < 3.0:  # unnaturally flat color (e.g. grayscale / poor print)
            score -= 0.30

        texture_live_score = float(np.clip(score, 0.05, 0.98))

        return {
            "texture_live_score": round(texture_live_score, 4),
            "moire_detected": moire_detected,
            "peak_ratio": round(float(peak_ratio), 3),
            "glare_detected": glare_detected,
            "glare_ratio": round(float(glare_ratio), 4),
            "skin_variance": round(float(cr_std + cb_std), 2),
        }
