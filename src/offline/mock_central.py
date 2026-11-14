"""Local demo receiver: durably acknowledge audit events without a remote server."""
import json
import os
import sqlite3


class MockCentral:
    def __init__(self, path="data/mock_central.sqlite3"):
        self.path = path

    def accept(self, events):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS audit_events (sync_id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            for event in events:
                db.execute("INSERT OR IGNORE INTO audit_events VALUES (?, ?)",
                           (event["sync_id"], json.dumps(event)))
        return [event["sync_id"] for event in events]

    def count(self):
        if not os.path.exists(self.path):
            return 0
        with sqlite3.connect(self.path) as db:
            try:
                return db.execute("SELECT COUNT(*) FROM audit_events").fetchone()[0]
            except sqlite3.OperationalError:
                return 0
