from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

YES_RE = re.compile(r"\b(да|выполнил|все|всё|полностью|закрыл)\b", re.I)
NO_RE = re.compile(r"\b(нет|не все|не всё|частично|осталось|не успел)\b", re.I)
WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def now_tz(tz_name: str = "Europe/Moscow") -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def date_key(d: date | datetime) -> str:
    if isinstance(d, datetime):
        d = d.date()
    return d.isoformat()


def format_date_ru(d: date) -> str:
    months = [
        "",
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ]
    weekdays = [
        "понедельник",
        "вторник",
        "среда",
        "четверг",
        "пятница",
        "суббота",
        "воскресенье",
    ]
    return f"{d.day} {months[d.month]} {d.year}, {weekdays[d.weekday()]}"


def week_bounds(d: date) -> tuple[date, date]:
    start = d - timedelta(days=d.weekday())  # Monday
    end = start + timedelta(days=6)
    return start, end


def bar(n: int, width: int = 4) -> str:
    filled = min(width, max(0, n))
    return "▓" * filled + "░" * (width - filled)


def approx_tasks_done(text: str) -> bool:
    if YES_RE.search(text) and not NO_RE.search(text):
        return True
    if NO_RE.search(text):
        return False
    return bool(text.strip()) and not NO_RE.search(text)


def has_carry(text: str) -> bool:
    t = text.strip().lower()
    if not t:
        return False
    if re.fullmatch(r"(нет|ничего|—|-|не\s*было)", t):
        return False
    return True


def truncate(s: str, n: int = 100) -> str:
    t = " ".join(s.strip().split())
    return t if len(t) <= n else t[: n - 1] + "…"


def build_weekly(entries: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    week_entries = [e for e in entries if date_key(start) <= e["date"] <= date_key(end)]
    by_weekday = [0] * 7
    tasks_done = 0
    carry = 0
    for e in week_entries:
        d = date.fromisoformat(e["date"])
        by_weekday[d.weekday()] += 1
        a = e["answers"]
        if approx_tasks_done(a.get("tasksDone", "")):
            tasks_done += 1
        if has_carry(a.get("carriedOver", "")):
            carry += 1

    lines = [
        f"Неделя {start.day} { _mon(start.month) } — {end.day} { _mon(end.month) } {end.year}: "
        f"{len(week_entries)} из 7 дней с сообщением.",
        f"Задачи «закрыты» (по тексту): ~{tasks_done} дн. Переносы на завтра: {carry} дн.",
    ]
    did_bits = []
    for e in sorted(week_entries, key=lambda x: x["date"]):
        text = (e["answers"].get("didToday") or "").strip()
        if text:
            wd = WEEKDAYS[date.fromisoformat(e["date"]).weekday()]
            did_bits.append(f"• {wd}: {truncate(text)}")
    if did_bits:
        lines.append("Кратко по делам:")
        lines.extend(did_bits[:7])
    summary = "\n".join(lines)

    suggestions: list[str] = []
    n = len(week_entries)
    if n < 5:
        suggestions.append(
            f"Стабильность записей: заполнено {n}/7. Цель — не пропускать 22:00."
        )
    else:
        suggestions.append(f"Ритм держался ({n}/7). Сохраните вечерний ритуал.")

    if n:
        ratio = tasks_done / n
        if ratio < 0.5:
            suggestions.append(
                "Дожим задач: чаще неполное закрытие. Сократите день до 3 главных пунктов."
            )
        else:
            suggestions.append(
                f"Закрытие задач ~{round(ratio * 100)}%. Можно чуть поднять объём."
            )

    if carry >= max(3, int(n * 0.6 + 0.999)):
        suggestions.append(
            "Хвост переносов — многое уходит на завтра. Закрывайте один «хвост» до обеда."
        )
    elif carry == 0 and n >= 3:
        suggestions.append("Чистый хвост переносов — сильный сигнал.")

    weak = [WEEKDAYS[i] for i, c in enumerate(by_weekday) if c == 0]
    if 0 < len(weak) < 7:
        suggestions.append(f"Слабые дни: {', '.join(weak)}. Напоминание именно на них.")

    weekday_bars = "\n".join(
        f"{WEEKDAYS[i]} {bar(by_weekday[i])} {by_weekday[i]}" for i in range(7)
    )

    review = {
        "id": f"week_{uuid.uuid4().hex[:8]}",
        "weekStart": date_key(start),
        "weekEnd": date_key(end),
        "createdAt": datetime.now().astimezone().isoformat(),
        "entryIds": [e["id"] for e in week_entries],
        "daysFilled": n,
        "daysInWeek": 7,
        "summaryText": summary,
        "suggestions": [
            {
                "id": f"s_{uuid.uuid4().hex[:6]}",
                "title": s.split("—")[0].split(":")[0][:40],
                "detail": s,
                "basedOn": "balance",
            }
            for s in suggestions[:5]
        ],
        "stats": {
            "entriesCount": n,
            "tasksFullyDoneApprox": tasks_done,
            "carryMentions": carry,
            "avgAnswerChars": 0,
        },
        "aiSummary": None,
        "_weekday_bars": weekday_bars,
        "_suggestion_lines": suggestions[:5],
        "_tasks_done": tasks_done,
        "_carry": carry,
    }
    return review


def _mon(m: int) -> str:
    return [
        "",
        "янв",
        "фев",
        "мар",
        "апр",
        "мая",
        "июн",
        "июл",
        "авг",
        "сен",
        "окт",
        "ноя",
        "дек",
    ][m]


def week_label(start: date, end: date) -> str:
    return f"{start.day}–{end.day} {_mon(end.month)} {end.year}"
