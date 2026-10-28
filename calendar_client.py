"""Клиент Календаря планов: HTTP API → fallback store JSON."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dates_ru import consume_date_and_time, resolve_date_phrase, today_moscow

log = logging.getLogger("agent-razbora-bot.calendar")


def _store_path() -> Path:
    root = Path(__file__).resolve().parent
    return Path(
        os.getenv(
            "CALENDAR_STORE_PATH",
            str(root / "data" / "plans-fallback.json"),
        )
    )


def _api_base() -> str:
    return os.getenv("CALENDAR_API_URL", "http://127.0.0.1:8080").rstrip("/")


def _api_key() -> str:
    return os.getenv("CALENDAR_API_KEY", "").strip()


@dataclass
class Plan:
    id: str
    title: str
    date: str
    time: str | None = None
    notes: str | None = None
    remindDate: str | None = None
    remindTime: str | None = None
    source: str | None = None
    chatId: str | None = None
    createdAt: str | None = None
    updatedAt: str | None = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Plan":
        return cls(
            id=str(d.get("id", "")),
            title=str(d.get("title", "")),
            date=str(d.get("date", "")),
            time=d.get("time") or None,
            notes=d.get("notes") or d.get("description") or None,
            remindDate=d.get("remindDate") or None,
            remindTime=d.get("remindTime") or None,
            source=d.get("source"),
            chatId=d.get("chatId"),
            createdAt=d.get("createdAt"),
            updatedAt=d.get("updatedAt"),
        )

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "date": self.date,
            "createdAt": self.createdAt,
            "updatedAt": self.updatedAt,
            "source": self.source or "telegram",
        }
        if self.time:
            out["time"] = self.time
        if self.notes:
            out["notes"] = self.notes
        if self.remindDate:
            out["remindDate"] = self.remindDate
        if self.remindTime:
            out["remindTime"] = self.remindTime
        if self.chatId:
            out["chatId"] = self.chatId
        return out


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _http(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_api_base()}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    key = _api_key()
    if key:
        headers["X-API-Key"] = key
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def api_available() -> bool:
    try:
        _http("GET", "/api/health")
        return True
    except Exception:
        return False


def _read_store() -> dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"plans": [], "updatedAt": _iso_now()}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"plans": [], "updatedAt": _iso_now()}


def _write_store(data: dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updatedAt"] = _iso_now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def list_plans(
    day: str | None = None, *, from_date: str | None = None, to_date: str | None = None
) -> list[Plan]:
    """Список планов. day=YYYY-MM-DD или диапазон from/to."""
    try:
        qs: dict[str, str] = {}
        if day:
            qs["date"] = day
        if from_date:
            qs["from"] = from_date
        if to_date:
            qs["to"] = to_date
        path = "/api/plans" + (("?" + urlencode(qs)) if qs else "")
        payload = _http("GET", path)
        plans = [Plan.from_dict(p) for p in payload.get("plans", [])]
        log.info("calendar HTTP: %s plan(s)", len(plans))
        return _sort(plans)
    except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError) as e:
        log.warning("calendar HTTP unavailable (%s) — store fallback", e)

    data = _read_store()
    plans = [Plan.from_dict(p) for p in data.get("plans", [])]
    if day:
        plans = [p for p in plans if p.date == day]
    else:
        if from_date:
            plans = [p for p in plans if p.date >= from_date]
        if to_date:
            plans = [p for p in plans if p.date <= to_date]
    return _sort(plans)


def create_plan(
    *,
    title: str,
    date: str,
    time: str | None = None,
    notes: str | None = None,
    remind_date: str | None = None,
    remind_time: str | None = None,
    chat_id: str | None = None,
    notify: bool = False,
) -> tuple[Plan, str]:
    """Создать план. Возвращает (plan, channel) где channel = http|store."""
    body: dict[str, Any] = {
        "title": title.strip(),
        "date": date,
        "source": "telegram",
        "notify": notify,
    }
    if time:
        body["time"] = time
    if notes:
        body["notes"] = notes
    if remind_date:
        body["remindDate"] = remind_date
    if remind_time:
        body["remindTime"] = remind_time
    if chat_id:
        body["chatId"] = str(chat_id)

    try:
        payload = _http("POST", "/api/plans", body)
        plan = Plan.from_dict(payload.get("plan") or payload)
        _mirror_upsert(plan)
        return plan, "http"
    except (URLError, HTTPError, TimeoutError, OSError, json.JSONDecodeError) as e:
        log.warning("calendar POST failed (%s) — store write", e)

    now = _iso_now()
    plan = Plan(
        id=str(uuid.uuid4()),
        title=title.strip(),
        date=date,
        time=time,
        notes=notes,
        remindDate=remind_date,
        remindTime=remind_time,
        source="telegram",
        chatId=str(chat_id) if chat_id else None,
        createdAt=now,
        updatedAt=now,
    )
    _mirror_upsert(plan)
    return plan, "store"


def _mirror_upsert(plan: Plan) -> None:
    data = _read_store()
    plans = [p for p in data.get("plans", []) if p.get("id") != plan.id]
    plans.append(plan.to_dict())
    data["plans"] = plans
    _write_store(data)


def _sort(plans: list[Plan]) -> list[Plan]:
    def key(p: Plan) -> tuple[str, str]:
        return (p.date, p.time or "99:99")

    return sorted(plans, key=key)


def format_plans(plans: list[Plan], heading: str) -> str:
    if not plans:
        return f"{heading}\n\nПока пусто."
    lines = [heading, ""]
    for i, p in enumerate(plans, 1):
        when = f"{p.time} · " if p.time else ""
        lines.append(f"{i}. {when}{p.title}")
        if p.remindDate or p.remindTime:
            r = "напомнить "
            if p.remindDate:
                r += p.remindDate
            if p.remindTime:
                r += f" {p.remindTime}"
            lines.append(f"   🔔 {r}")
        if p.notes:
            lines.append(f"   {p.notes}")
    return "\n".join(lines)


# --- парсер: запиши … сегодня/завтра … в 15, напомни … ---

_CMD = re.compile(r"^(?:запиши(?:\s+план)?|add)\s+", re.IGNORECASE)

_REMIND_SPLIT = re.compile(r",?\s*напомни(?:ть)?\s+", re.IGNORECASE)

_REMIND_OFFSET = re.compile(
    r"""^за\s+(?:(?P<n>\d+)\s+)?(?P<u>день|дня|дней)
        (?:\s+(?:в|на)\s+(?P<time>\d{1,2}(?::\d{2})?))?
        \s*(?P<rest>.*)$""",
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

_REMIND_TIME_ONLY = re.compile(
    r"^(?:в|на)\s+(?P<time>\d{1,2}(?::\d{2})?)\s*(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def normalize_time(s: str) -> str:
    s = s.strip()
    if ":" in s:
        h, mi = s.split(":", 1)
        return f"{int(h):02d}:{int(mi):02d}"
    return f"{int(s):02d}:00"


def parse_add_command(
    text: str,
    *,
    default_year: int | None = None,  # noqa: ARG001
    today: date | None = None,
) -> dict[str, str | None]:
    """
    Примеры:
      запиши встречу с отцом сегодня в 15, напомни сегодня в 13:37
      запиши завтра встреча с отцом на 15, напомни в 13:20
      запиши в среду созвон на 15:30, напомни за день в 10:00
    """
    raw = text.strip()
    if not _CMD.match(raw):
        raise ValueError(
            "Формат: запиши встречу с отцом сегодня в 15, напомни сегодня в 13:37"
        )

    body = _CMD.sub("", raw, count=1).strip()
    today = today or today_moscow()

    parts = _REMIND_SPLIT.split(body, maxsplit=1)
    event_part = parts[0].strip(" ,;—-")
    remind_part = parts[1].strip(" ,;—-") if len(parts) > 1 else ""

    try:
        event_date, event_time, title = consume_date_and_time(event_part, today=today)
    except ValueError as e:
        raise ValueError(
            f"{e}\nПример: запиши встречу с отцом сегодня в 15, напомни в 13:37"
        ) from e

    # Кавычки вокруг названия
    qm = re.match(r'^["«](.+?)["»]\s*(.*)$', title.strip(), re.DOTALL)
    notes = ""
    if qm:
        title = qm.group(1).strip()
        notes = qm.group(2).strip()

    title = re.sub(r"\s+", " ", title).strip(" ,;—-")
    # убрать хвосты вроде «сегодня» если вдруг остались
    title = re.sub(
        r"\b(сегодня|завтра|послезавтра|вчера)\b",
        "",
        title,
        flags=re.I,
    )
    title = re.sub(r"\s+", " ", title).strip(" ,;—-")
    # «запиши встречу» → именительный для календаря
    title = re.sub(r"(?i)^встречу\b", "встреча", title)
    title = re.sub(r"(?i)^созвон[ае]\b", "созвон", title)
    if not title:
        raise ValueError(
            "Не нашёл название. Пример: запиши встречу с отцом сегодня в 15"
        )

    remind_date = None
    remind_time = None

    if remind_part:
        om = _REMIND_OFFSET.match(remind_part)
        to = _REMIND_TIME_ONLY.match(remind_part)
        if om:
            n = int(om.group("n") or "1")
            ed = date.fromisoformat(event_date)
            remind_date = (ed - timedelta(days=n)).isoformat()
            if om.group("time"):
                remind_time = normalize_time(om.group("time"))
            notes = (notes + " " + (om.group("rest") or "")).strip(" ,;—-")
        elif to:
            remind_date = event_date
            remind_time = normalize_time(to.group("time"))
            notes = (notes + " " + (to.group("rest") or "")).strip(" ,;—-")
        else:
            try:
                remind_date, r_time, after_remind = consume_date_and_time(
                    remind_part, today=today
                )
                remind_time = r_time
                if not remind_time:
                    m3 = re.match(
                        r"^(?:в|на)\s+(\d{1,2}(?::\d{2})?)\s*(.*)$",
                        after_remind.strip(),
                        re.I,
                    )
                    if m3:
                        remind_time = normalize_time(m3.group(1))
                        after_remind = m3.group(2)
                notes = (notes + " " + after_remind).strip(" ,;—-")
            except ValueError:
                notes = (notes + " напомни " + remind_part).strip(" ,;—-")

    notes = re.sub(r"^(описание[:\s]+)", "", notes or "", flags=re.I).strip(" ,;—-")

    return {
        "title": title,
        "date": event_date,
        "time": event_time,
        "notes": notes or None,
        "remindDate": remind_date,
        "remindTime": remind_time,
    }


def normalize_date(
    s: str, *, default_year: int | None = None, today: date | None = None
) -> str:
    """Числовая или относительная дата → YYYY-MM-DD."""
    today = today or today_moscow()
    _ = default_year
    return resolve_date_phrase(s, today=today).isoformat()
