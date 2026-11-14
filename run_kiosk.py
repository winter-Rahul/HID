"""
HID Fortified-PAD Kiosk Launcher
"""
import os
import sys

# Ensure Intel OpenMP does not crash
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("  🚀 HID LIVENESS DETECTION & AUTHENTICATION KIOSK")
    print("  Challenge: Can You Spot a Spoof? (≤ 2.0s Decision Budget)")
    print("="*60)
    print("\n  👉 Kiosk Web UI: http://127.0.0.1:8000\n")
    print("  Press CTRL+C to stop.\n" + "="*60 + "\n")

    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, log_level="info")
