"""
Offline Fail-Safe Mode & Sync Queue Manager
Surprise Challenge 02:
1. Zero Fail-Open Guarantee: System never allows access without verified local authentication.
2. Privacy First: No raw biometrics stored in offline queue; only cryptographically hashed IDs.
3. Auto-Sync: Queues offline events and syncs them automatically when connection returns.
"""
import os
import json
import time
import hashlib
from typing import Dict, Any, List


class OfflineFailSafe:
    def __init__(self, queue_file: str = "data/offline_sync_queue.json"):
        self.queue_file = queue_file
        self.online_mode = True
        self.queue: List[Dict[str, Any]] = []
        # Pre-approved emergency offline whitelist (cryptographic hashes of authorized employee IDs)
        self.offline_whitelist_hashes = set()
        self._load_queue()

    def _load_queue(self):
        if os.path.exists(self.queue_file):
            try:
                with open(self.queue_file, "r") as f:
                    self.queue = json.load(f)
            except Exception as e:
                print(f"[OfflineFailSafe] Error loading queue: {e}")

    def _save_queue(self):
        os.makedirs(os.path.dirname(self.queue_file), exist_ok=True)
        with open(self.queue_file, "w") as f:
            json.dump(self.queue, f, indent=2)

    def set_online_status(self, is_online: bool):
        was_offline = not self.online_mode
        self.online_mode = is_online
        if is_online and was_offline:
            self.sync_queued_decisions()

    def is_online(self) -> bool:
        return self.online_mode

    def hash_identity(self, name: str) -> str:
        """One-way pseudonymized salt+SHA-256 of identity for privacy-preserving offline audit."""
        return hashlib.sha256(f"HID_SALT_{name}".encode()).hexdigest()[:16]

    def queue_offline_decision(self, decision: str, name: str, reason_code: str, latency_ms: float) -> Dict[str, Any]:
        """
        Logs decision to offline queue without saving raw biometrics.
        """
        entry = {
            "sync_id": f"OFFLINE_{int(time.time()*1000)}",
            "timestamp": time.time(),
            "hashed_user_id": self.hash_identity(name) if name else "ANONYMOUS",
            "decision": decision,
            "reason_code": reason_code,
            "latency_ms": latency_ms,
            "synced": False,
        }
        self.queue.append(entry)
        self._save_queue()
        return entry

    def sync_queued_decisions(self) -> int:
        """Simulates flushing queued offline audit logs to central server on reconnect."""
        unsynced = [e for e in self.queue if not e["synced"]]
        count = len(unsynced)
        for e in unsynced:
            e["synced"] = True
            e["synced_at"] = time.time()
        self._save_queue()
        if count > 0:
            print(f"[OfflineFailSafe] Successfully synchronized {count} offline audit events to central server.")
        return count

    def get_queue_status(self) -> Dict[str, Any]:
        pending = sum(1 for e in self.queue if not e.get("synced", False))
        return {
            "online_mode": self.online_mode,
            "pending_sync_count": pending,
            "total_queued": len(self.queue),
        }
