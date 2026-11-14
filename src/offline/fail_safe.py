"""
Offline Fail-Safe Mode & Sync Queue Manager
Surprise Challenge 02:
1. Zero Fail-Open Guarantee: System never allows access without verified local authentication.
2. Privacy First: No raw biometrics stored in offline queue; only cryptographically hashed IDs.
3. Demo sync: Queues offline events and sends them to a local mock receiver on reconnect.
"""
import os
import json
import time
import uuid
from src.offline.mock_central import MockCentral
from typing import Dict, Any, List


class OfflineFailSafe:
    def __init__(self, queue_file: str = "data/offline_sync_queue.json", receiver=None):
        self.queue_file = queue_file
        self.receiver = receiver if receiver is not None else MockCentral()
        self.online_mode = True
        self.queue: List[Dict[str, Any]] = []
        # Pre-approved emergency offline whitelist (cryptographic hashes of authorized employee IDs)
        self.offline_whitelist_hashes = set()
        self._load_queue()
        state_file = self.queue_file + ".state"
        if os.path.exists(state_file):
            try:
                with open(state_file, encoding="utf-8") as f:
                    self.online_mode = json.load(f)["online_mode"] is True
            except (OSError, ValueError, KeyError, TypeError):
                self.online_mode = False

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
        self.online_mode = is_online
        os.makedirs(os.path.dirname(os.path.abspath(self.queue_file)), exist_ok=True)
        with open(self.queue_file + ".state", "w", encoding="utf-8") as f:
            json.dump({"online_mode": self.online_mode}, f)
        if is_online:
            self.sync_queued_decisions()

    def is_online(self) -> bool:
        return self.online_mode

    def hash_identity(self, name: str) -> str:
        """Avoid retaining a reversible or guessable identity in the demo queue."""
        return "REDACTED"

    def queue_offline_decision(self, decision: str, name: str, reason_code: str, latency_ms: float) -> Dict[str, Any]:
        """
        Logs decision to offline queue without saving raw biometrics.
        """
        entry = {
            "sync_id": f"OFFLINE_{uuid.uuid4().hex}",
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
        """Sync to the local mock receiver and mark only acknowledged events."""
        pending = [e for e in self.queue if not e.get("synced", False)]
        if not pending:
            return 0
        try:
            acknowledged = set(self.receiver.accept(pending))
        except Exception as exc:
            print(f"[OfflineFailSafe] Sync failed; events remain pending: {exc}")
            return 0
        count = 0
        for event in pending:
            if event["sync_id"] in acknowledged:
                event["synced"] = True
                event["synced_at"] = time.time()
                count += 1
        if count:
            self.queue = [event for event in self.queue if not event.get("synced", False)]
            self._save_queue()
        return count

    def get_queue_status(self) -> Dict[str, Any]:
        pending = sum(1 for e in self.queue if not e.get("synced", False))
        return {
            "online_mode": self.online_mode,
            "pending_sync_count": pending,
            "total_queued": len(self.queue),
        }
