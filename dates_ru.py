"""Русские относительные даты → YYYY-MM-DD (Europe/Moscow по умолчанию)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# weekday() : Mon=0 … Sun=6
WEEKDAY_ALIASES: dict[str, int] = {
    "понедельник": 0,
    "пон": 0,
    "пн": 0,
    "вторник": 1,
    "вт": 1,
    "среда": 2,
    "среду": 2,
    "ср": 2,
    "четверг": 3,
    "чт": 3,
    "пятница": 4,
    "пятницу": 4,
    "пт": 4,
    "суббота": 5,
    "субботу": 5,
    "сб": 5,
    "воскресенье": 6,
    "воскресенья": 6,
    "вс": 6,
}

# Короткие коды — только целым словом (иначе «встречу» → вс)
_SHORT_WD = {"пн", "вт", "ср", "чт", "пт", "сб", "вс", "пон"}
_WEEKDAY_ALT = "|".join(
    sorted((re.escape(k) for k in WEEKDAY_ALIASES), key=len, reverse=True)
)
# Граница слова для кириллицы/латиницы
_B = r"(?<![0-9A-Za-zА-Яа-яЁё])"
_E = r"(?![0-9A-Za-zА-Яа-яЁё])"

_REL_CORE = rf"""
    сегодня|завтра|послезавтра|вчера
  | через\s+\d+\s+(?:день|дня|дней|неделю|недели|недель)
  | через\s+неделю
  | на\s+этой\s+неделе\s+(?:во?\s+)?(?:{_WEEKDAY_ALT})
  | на\s+следующей\s+неделе\s+(?:во?\s+)?(?:{_WEEKDAY_ALT})
  | (?:во?\s+)?(?:{_WEEKDAY_ALT})\s+на\s+(?:этой|следующей)\s+неделе
  | следующ(?:ий|ую|ей|е)\s+(?:{_WEEKDAY_ALT})
  | (?:во?\s+)?(?:{_WEEKDAY_ALT})
"""

# Дата где угодно в тексте (не якорь ^)
_DATE_FIND = re.compile(
    rf"""
    {_B}
    (?:
        (?P<iso>\d{{4}}-\d{{2}}-\d{{2}})
      | (?P<dmy>\d{{1,2}}[./]\d{{1,2}}(?:[./]\d{{2,4}})?)
      | (?P<rel>{_REL_CORE})
    )
    {_E}
    """,
    re.IGNORECASE | re.VERBOSE,
)

_TIME_TOKEN = re.compile(
    r"(?:^|(?<=\s)|(?<=,))(?:на|в)\s+(?P<time>\d{1,2}(?::\d{2})?)\b",
    re.IGNORECASE,
)


def today_moscow(tz_name: str = "Europe/Moscow") -> date:
    return datetime.now(ZoneInfo(tz_name)).date()


def monday_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def next_weekday(
    from_day: date, target: int, *, weeks_ahead: int = 0, allow_today: bool = False
) -> date:
    if weeks_ahead:
        base = monday_of(from_day) + timedelta(weeks=weeks_ahead)
        return base + timedelta(days=target)
    delta = (target - from_day.weekday()) % 7
    if delta == 0 and not allow_today:
        delta = 7
    return from_day + timedelta(days=delta)


def resolve_date_phrase(phrase: str, *, today: date | None = None) -> date:
    """Разобрать одно выражение даты → date."""
    today = today or today_moscow()
    s = " ".join(phrase.strip().lower().split())
    if not s:
        raise ValueError("Пустая дата")

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return date.fromisoformat(s)

    m = re.fullmatch(r"(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        if y < 100:
            y += 2000
        cand = date(y, mo, d)
        if not m.group(3) and cand < today:
            cand = date(y + 1, mo, d)
        return cand

    if s == "сегодня":
        return today
    if s == "завтра":
        return today + timedelta(days=1)
    if s == "послезавтра":
        return today + timedelta(days=2)
    if s == "вчера":
        return today - timedelta(days=1)

    m = re.fullmatch(r"через\s+(\d+)\s+(день|дня|дней|неделю|недели|недель)", s)
    if m:
        n = int(m.group(1))
        unit = m.group(2)
        if unit.startswith("недел"):
            return today + timedelta(weeks=n)
        return today + timedelta(days=n)

    if s == "через неделю":
        return today + timedelta(weeks=1)

    m = re.fullmatch(rf"следующ(?:ий|ую|ей|е)\s+({_WEEKDAY_ALT})", s)
    if m:
        wd = m.group(1).lower()
        return next_weekday(today, WEEKDAY_ALIASES[wd], weeks_ahead=0, allow_today=False)

    m = re.fullmatch(rf"на\s+следующей\s+неделе\s+(?:во?\s+)?({_WEEKDAY_ALT})", s)
    if m:
        return next_weekday(
            today, WEEKDAY_ALIASES[m.group(1).lower()], weeks_ahead=1, allow_today=True
        )

    m = re.fullmatch(rf"на\s+этой\s+неделе\s+(?:во?\s+)?({_WEEKDAY_ALT})", s)
    if m:
        wd = WEEKDAY_ALIASES[m.group(1).lower()]
        base = monday_of(today) + timedelta(days=wd)
        if base < today:
            return next_weekday(today, wd, weeks_ahead=0, allow_today=False)
        return base

    m = re.fullmatch(
        rf"(?:во?\s+)?({_WEEKDAY_ALT})\s+на\s+(этой|следующей)\s+неделе", s
    )
    if m:
        wd = WEEKDAY_ALIASES[m.group(1).lower()]
        if m.group(2) == "следующей":
            return next_weekday(today, wd, weeks_ahead=1, allow_today=True)
        base = monday_of(today) + timedelta(days=wd)
        if base < today:
            return next_weekday(today, wd, weeks_ahead=0, allow_today=False)
        return base

    m = re.fullmatch(rf"(?:во?\s+)?({_WEEKDAY_ALT})", s)
    if m:
        wd_name = m.group(1).lower()
        # защита: короткие коды только как целые слова (fullmatch уже ок)
        return next_weekday(
            today, WEEKDAY_ALIASES[wd_name], weeks_ahead=0, allow_today=True
        )

    raise ValueError(f"Непонятная дата: {phrase}")


def find_date_match(text: str) -> re.Match[str] | None:
    """Найти первое валидное вхождение даты; короткие «вс» внутри слов отсекаются границами."""
    for m in _DATE_FIND.finditer(text):
        rel = m.group("rel")
        if rel:
            # дополнительная проверка коротких weekday
            core = rel.strip().lower()
            core = re.sub(r"^(во?\s+)", "", core)
            first = core.split()[0] if core else ""
            if first in _SHORT_WD:
                # уже с границами в regex — ок
                pass
        return m
    return None


def consume_date_and_time(
    text: str, *, today: date | None = None, require_start: bool = False
) -> tuple[str, str | None, str]:
    """
    Съесть дату (+ опционально время рядом).
    Если require_start=False — дата может быть в середине («встречу … сегодня в 15»).
    Возвращает (YYYY-MM-DD, HH:mm|None, текст без даты/этого времени).
    """
    today = today or today_moscow()
    if require_start:
        m = _DATE_FIND.match(text)
    else:
        m = find_date_match(text)
        # предпочесть дату в начале, если есть
        m0 = _DATE_FIND.match(text.lstrip())
        if m0:
            # пересчитать с учётом leading space
            lead = len(text) - len(text.lstrip())
            if m0.start() == 0 or True:
                # match on lstrip — adjust
                m_start = _DATE_FIND.search(text, lead)
                if m_start and m_start.start() == lead:
                    m = m_start

    if not m:
        raise ValueError(
            "Не нашёл дату. Примеры: сегодня, завтра, в среду, 28.10"
        )

    if m.group("iso"):
        phrase = m.group("iso")
    elif m.group("dmy"):
        phrase = m.group("dmy")
    else:
        phrase = m.group("rel")

    resolved = resolve_date_phrase(phrase.strip(), today=today)

    # Убрать дату из текста
    before = text[: m.start()]
    after = text[m.end() :]
    combined = f"{before} {after}"
    combined = re.sub(r"\s+", " ", combined).strip(" ,;—-")

    # Время: «в 15» / «на 15:30» — берём последнее перед концом или первое после даты
    time_s = None
    tm = None
    # сначала сразу после даты в after
    tm = re.match(
        r"^\s*(?:в|на)\s+(?P<time>\d{1,2}(?::\d{2})?)\b", after, re.I
    )
    if tm:
        time_s = _norm_time(tm.group("time"))
        after2 = after[tm.end() :]
        combined = f"{before} {after2}".strip()
        combined = re.sub(r"\s+", " ", combined).strip(" ,;—-")
    else:
        # в оставшемся тексте — последнее «в/на N»
        matches = list(_TIME_TOKEN.finditer(combined))
        if matches:
            tm = matches[-1]
            time_s = _norm_time(tm.group("time"))
            combined = (combined[: tm.start()] + " " + combined[tm.end() :]).strip()
            combined = re.sub(r"\s+", " ", combined).strip(" ,;—-")

    return resolved.isoformat(), time_s, combined


def _norm_time(s: str) -> str:
    if ":" in s:
        h, mi = s.split(":", 1)
        return f"{int(h):02d}:{int(mi):02d}"
    return f"{int(s):02d}:00"
