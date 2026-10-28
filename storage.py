from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from messages import EMPTY_ANSWERS

DEFAULT = {
    "version": 1,
    "chat_id": None,
    "entries": [],
    "weeklyReviews": [],
    "pending": None,  # {date, step, answers}
    "settings": {
        "eveningHour": 22,
        "eveningMinute": 0,
        "weeklyHour": 18,
        "weeklyMinute": 0,
        "timezone": "Europe/Moscow",
    },
}


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            data = deepcopy(DEFAULT)
            self._write(data)
            return data
        with self.path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        data = deepcopy(DEFAULT)
        data.update({k: raw.get(k, v) for k, v in DEFAULT.items()})
        data["settings"] = {**DEFAULT["settings"], **(raw.get("settings") or {})}
        return data

    def _write(self, data: dict[str, Any] | None = None) -> None:
        payload = data if data is not None else self._data
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        tmp.replace(self.path)

    def save(self) -> None:
        self._write()

    @property
    def chat_id(self) -> int | None:
        return self._data.get("chat_id")

    def set_chat_id(self, chat_id: int) -> None:
        self._data["chat_id"] = chat_id
        self.save()

    def entry_for(self, date_key: str) -> dict[str, Any] | None:
        for e in self._data["entries"]:
            if e["date"] == date_key:
                return e
        return None

    def pending(self) -> dict[str, Any] | None:
        return self._data.get("pending")

    def clear_pending(self) -> None:
        self._data["pending"] = None
        self.save()

    def start_pending(self, date_key: str) -> dict[str, Any]:
        pending = {
            "date": date_key,
            "step": 0,
            "answers": dict(EMPTY_ANSWERS),
        }
        self._data["pending"] = pending
        self.save()
        return pending

    def previous_entry(self, date_key: str) -> dict[str, Any] | None:
        """Запись за день до date_key (для «сегодня планировалось»)."""
        from datetime import date, timedelta

        d = date.fromisoformat(date_key) - timedelta(days=1)
        return self.entry_for(d.isoformat())

    def update_pending_answer(self, field: str, text: str) -> dict[str, Any]:
        pending = self._data["pending"]
        assert pending is not None
        pending["answers"][field] = text.strip()
        pending["step"] = int(pending["step"]) + 1
        self.save()
        return pending

    def commit_pending(self) -> dict[str, Any]:
        pending = self._data["pending"]
        assert pending is not None
        if self.entry_for(pending["date"]):
            raise ValueError("already_saved")
        entry = {
            "id": f"day_{uuid.uuid4().hex[:8]}",
            "date": pending["date"],
            "createdAt": datetime.now().astimezone().isoformat(),
            "answers": dict(pending["answers"]),
        }
        self._data["entries"].append(entry)
        self._data["pending"] = None
        self.save()
        return entry

    def entries_in_range(self, start: str, end: str) -> list[dict[str, Any]]:
        return [e for e in self._data["entries"] if start <= e["date"] <= end]

    def all_entries(self) -> list[dict[str, Any]]:
        return list(self._data["entries"])

    def weekly_for(self, week_start: str) -> dict[str, Any] | None:
        for w in self._data["weeklyReviews"]:
            if w["weekStart"] == week_start:
                return w
        return None

    def add_weekly(self, review: dict[str, Any]) -> None:
        self._data["weeklyReviews"] = [
            r for r in self._data["weeklyReviews"] if r["weekStart"] != review["weekStart"]
        ]
        self._data["weeklyReviews"].insert(0, review)
        self.save()

    def export_web_compatible(self) -> dict[str, Any]:
        """Подмножество, близкое к web AppData (без pending/chat_id)."""
        return {
            "version": 1,
            "entries": self._data["entries"],
            "weeklyReviews": self._data["weeklyReviews"],
            "settings": {
                "eveningHour": self._data["settings"]["eveningHour"],
                "eveningMinute": self._data["settings"]["eveningMinute"],
                "weeklyHour": self._data["settings"]["weeklyHour"],
                "weeklyMinute": self._data["settings"]["weeklyMinute"],
                "notifyPermissionAsked": False,
                "questionLabels": {
                    "tasksTomorrow": "Задачи на завтра",
                    "sinkClean": "Чистая раковина перед отбоем",
                    "exercise": "Зарядка",
                    "threeMeals": "3 полных приёма пищи",
                    "groupVisit": "Посещение группы",
                },
            },
        }
