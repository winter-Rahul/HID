"""
HID Fortified-PAD Kiosk Launcher
"""
import os
import sys
import secrets
from pathlib import Path

# Ensure Intel OpenMP does not crash
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

if __name__ == "__main__":
    import uvicorn
    env_path = Path(__file__).resolve().parent / ".env"
    if not os.environ.get("HID_ADMIN_TOKEN") and env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == "HID_ADMIN_TOKEN":
                os.environ["HID_ADMIN_TOKEN"] = value.strip().strip('"\'')
                break
    if not os.environ.get("HID_ADMIN_TOKEN"):
        token_path = Path("data/.admin_token")
        token_path.parent.mkdir(parents=True, exist_ok=True)
        if not token_path.exists():
            with token_path.open("x", encoding="utf-8") as token_file:
                token_file.write(secrets.token_urlsafe(32))
        os.environ["HID_ADMIN_TOKEN"] = token_path.read_text(encoding="utf-8").strip()
        if not os.environ["HID_ADMIN_TOKEN"]:
            raise RuntimeError("The local management token file is empty")
        print(f"Management token is stored in {token_path.resolve()}; enter it when prompted.")
    print("\n" + "="*60)
    print("  🚀 HID LIVENESS DETECTION & AUTHENTICATION KIOSK")
    print("  Challenge: Can You Spot a Spoof? (≤ 2.0s Decision Budget)")
    print("="*60)
    print("\n  👉 Kiosk Web UI: http://127.0.0.1:8000\n")
    print("  Press CTRL+C to stop.\n" + "="*60 + "\n")

    uvicorn.run("src.server:app", host="127.0.0.1", port=8000, log_level="info")
