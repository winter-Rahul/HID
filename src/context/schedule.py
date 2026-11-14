"""
Context-Aware Campus Access Schedule Manager
Surprise Challenge 01: Cross-reference biometric identity with access schedule permissions.
Liveness alone does NOT grant access.
"""
import os
import json
import datetime
from typing import Dict, Any, List, Optional


class ScheduleManager:
    def __init__(self, schedule_file: str = "data/campus_schedules.json"):
        self.schedule_file = schedule_file
        self.schedules: Dict[str, Dict[str, Any]] = {
            # Default profiles
            "Alex Morgan": {
                "role": "Software Engineer",
                "department": "Engineering",
                "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                "start_hour": 8,
                "end_hour": 18,
                "allowed_zones": ["Building A", "Main Gate", "Labs"],
                "emergency_override": False,
            },
            "Security Officer": {
                "role": "Campus Security",
                "department": "Facilities",
                "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
                "start_hour": 0,
                "end_hour": 24,
                "allowed_zones": ["All"],
                "emergency_override": True,
            },
            "Visiting Guest": {
                "role": "Vendor",
                "department": "Visitor",
                "days": ["Mon", "Wed"],
                "start_hour": 10,
                "end_hour": 14,
                "allowed_zones": ["Main Reception"],
                "emergency_override": False,
            },
            "Night Contractor": {
                "role": "Maintenance",
                "department": "Operations",
                "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                "start_hour": 22,
                "end_hour": 4, # Overnight
                "allowed_zones": ["Building B"],
                "emergency_override": False,
            }
        }
        self._load()

    def _load(self):
        if os.path.exists(self.schedule_file):
            try:
                with open(self.schedule_file, "r") as f:
                    self.schedules = json.load(f)
            except Exception as e:
                print(f"[ScheduleManager] Error loading {self.schedule_file}: {e}")
                self.schedules = {}
        else:
            self._save()

    def _save(self):
        os.makedirs(os.path.dirname(self.schedule_file), exist_ok=True)
        with open(self.schedule_file, "w") as f:
            json.dump(self.schedules, f, indent=2)

    def set_user_schedule(self, name: str, start_hour: int, end_hour: int, days: List[str]):
        self.schedules[name] = {
            "role": "Employee",
            "department": "Campus Staff",
            "days": days,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "allowed_zones": ["Main Gate", "Offices"],
            "emergency_override": False,
        }
        self._save()

    def check_access(self, name: str, simulated_hour: Optional[int] = None, simulated_day: Optional[str] = None) -> Dict[str, Any]:
        """
        Validates if user is authorized to enter campus at the current or simulated time.
        """
        now = datetime.datetime.now()
        hour = simulated_hour if simulated_hour is not None else now.hour
        day_name = simulated_day if simulated_day is not None else now.strftime("%a")

        if name not in self.schedules:
            return {"allowed": False, "reason": "No authorized schedule", "current_hour": hour}
        else:
            sched = self.schedules[name]

        if sched.get("emergency_override", False):
            return {
                "allowed": True,
                "reason": "Emergency security 24/7 access grant",
                "current_hour": hour,
                "schedule_window": f"{sched['start_hour']:02d}:00 - {sched['end_hour']:02d}:00",
            }

        # Check day
        start = sched.get("start_hour", 8)
        end = sched.get("end_hour", 18)
        days = sched.get("days", [])
        # The early-morning part of an overnight shift belongs to its start day.
        if start > end and hour < end:
            weekday_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            if day_name in weekday_names:
                day_name = weekday_names[(weekday_names.index(day_name) - 1) % 7]
        if day_name not in days:
            return {
                "allowed": False,
                "reason": f"Access denied: Not authorized on {day_name}",
                "current_hour": hour,
                "schedule_window": f"{sched['start_hour']:02d}:00 - {sched['end_hour']:02d}:00",
            }

        # Check hour
        start = sched.get("start_hour", 8)
        end = sched.get("end_hour", 18)

        if start <= end:
            in_window = (start <= hour < end)
        else:
            # Overnight shift
            in_window = (hour >= start or hour < end)

        if not in_window:
            return {
                "allowed": False,
                "reason": f"Schedule Violation: Access window {start:02d}:00–{end:02d}:00 (Attempt at {hour:02d}:00)",
                "current_hour": hour,
                "schedule_window": f"{start:02d}:00 - {end:02d}:00",
            }

        return {
            "allowed": True,
            "reason": f"Within scheduled hours ({start:02d}:00–{end:02d}:00)",
            "current_hour": hour,
            "schedule_window": f"{start:02d}:00 - {end:02d}:00",
        }
