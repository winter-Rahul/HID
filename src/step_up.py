"""Local PIN verifier for short-lived, rate-limited demo step-up challenges."""
import hashlib
import hmac
import json
import os
import secrets
import time


class StepUp:
    def __init__(self, path="data/step_up_pins.json"):
        self.path = path
        self.challenges = {}
        self.failures = {}

    def _load(self):
        if not os.path.exists(self.path):
            return {}
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def set_pin(self, name, pin):
        if not (pin.isascii() and pin.isdigit() and 6 <= len(pin) <= 12):
            raise ValueError("PIN must contain 6 to 12 digits")
        records = self._load()
        salt = os.urandom(16)
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 310000)
        records[name] = {"salt": salt.hex(), "digest": digest.hex()}
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(records, f)
        os.replace(tmp, self.path)

    def remove_pin(self, name):
        records = self._load()
        if name in records:
            del records[name]
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(records, f)
        self.challenges = {k: v for k, v in self.challenges.items() if v["name"] != name}

    def issue(self, name):
        now = time.monotonic()
        self.challenges = {k: v for k, v in self.challenges.items() if v["expires"] > now}
        if name not in self._load() or self.failures.get(name, (0, 0))[1] > now:
            return None
        token = secrets.token_urlsafe(32)
        self.challenges[token] = {"name": name, "expires": now + 60}
        return token

    def verify(self, token, pin):
        challenge = self.challenges.pop(token, None)
        now = time.monotonic()
        if challenge is None or challenge["expires"] <= now:
            return None
        name = challenge["name"]
        count, locked_until = self.failures.get(name, (0, 0))
        if locked_until > now:
            return None
        if locked_until and locked_until <= now:
            count = 0
        record = self._load().get(name)
        if not record or not (pin.isascii() and pin.isdigit() and 6 <= len(pin) <= 12):
            return None
        digest = hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(record["salt"]), 310000).hex()
        if not hmac.compare_digest(digest, record["digest"]):
            count += 1
            self.failures[name] = (count, now + 60 if count >= 3 else 0)
            return None
        self.failures.pop(name, None)
        return name
