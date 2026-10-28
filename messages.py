"""Шаблоны сообщений бота «Агент разбора»."""

from __future__ import annotations

# (field, label, kind) — kind: tasks | pm
QUESTION_SPECS: tuple[tuple[str, str, str], ...] = (
    ("tasksTomorrow", "Задачи на завтра", "tasks"),
    ("sinkClean", "Чистая раковина перед отбоем", "pm"),
    ("exercise", "Зарядка", "pm"),
    ("threeMeals", "3 полных приёма пищи", "pm"),
    ("groupVisit", "Посещение группы", "pm"),
)

QUESTIONS = tuple(q[1] for q in QUESTION_SPECS)
QUESTION_FIELDS = tuple(q[0] for q in QUESTION_SPECS)
QUESTION_KINDS = tuple(q[2] for q in QUESTION_SPECS)

EMPTY_ANSWERS = {f: "" for f in QUESTION_FIELDS}


def format_planned_block(planned_lines: list[str] | None) -> str:
    if not planned_lines:
        return "Сегодня планировалось — —\n(вчера список задач на сегодня не оставляли)"
    bullets = "\n".join(f"• {x}" for x in planned_lines)
    return f"Сегодня планировалось —\n{bullets}"


def daily_prompt(date_label: str, planned_lines: list[str] | None = None) -> str:
    lines = [
        f"🌙 Вечерний разбор · {date_label}",
        "",
        "Одно сообщение на день. После ответа править нельзя.",
        "",
        format_planned_block(planned_lines),
        "",
        "Ответьте по очереди на 5 вопросов:",
        "",
        "1) Задачи на завтра (список → появятся в /tasks)",
        "2) Чистая раковина перед отбоем (+/−)",
        "3) Зарядка (+/−)",
        "4) 3 полных приёма пищи (+/−)",
        "5) Посещение группы (+/−)",
        "",
        "Напишите ответ на вопрос 1 — список задач на завтра "
        "(с новой строки или через запятую; «нет» / «—», если задач нет).",
    ]
    return "\n".join(lines)


def ask_question(index: int) -> str:
    label = QUESTIONS[index]
    kind = QUESTION_KINDS[index]
    n = len(QUESTIONS)
    if kind == "pm":
        return f"{index + 1}/{n} · {label}\nОтветьте + или − (да/нет тоже подойдут)."
    return (
        f"{index + 1}/{n} · {label}\n"
        "Список задач на завтра (с новой строки или через запятую).\n"
        "Они попадут в /tasks. «нет» / «—» — если задач нет."
    )


def daily_saved(date_label: str, answers: dict[str, str]) -> str:
    habits = (
        f"Раковина {answers.get('sinkClean', '—')} · "
        f"Зарядка {answers.get('exercise', '—')} · "
        f"Еда {answers.get('threeMeals', '—')} · "
        f"Группа {answers.get('groupVisit', '—')}"
    )
    tasks = answers.get("tasksTomorrow", "").strip() or "—"
    return (
        f"✅ Сообщение за {date_label} записано.\n"
        f"\n"
        f"• Задачи на завтра:\n{tasks}\n"
        f"• Привычки: {habits}\n"
        f"\n"
        f"До завтра в 22:00. Правки закрыты."
    )


def already_saved(date_label: str) -> str:
    return (
        f"На {date_label} сообщение уже есть.\n"
        f"Одно в день, править нельзя. Увидимся завтра в 22:00."
    )


def weekly_stats_message(
    *,
    week_label: str,
    days_filled: int,
    tasks_done: int,
    carry: int,
    weekday_bars: str,
    summary: str,
    suggestions: list[str],
) -> str:
    tips = (
        "\n".join(f"→ {s}" for s in suggestions)
        if suggestions
        else "→ Пока мало данных — продолжайте писать в 22:00."
    )
    return (
        f"📊 Итог недели · {week_label}\n"
        f"\n"
        f"Заполнено дней: {days_filled}/7\n"
        f"Привычки «+» (оценка): ~{tasks_done}\n"
        f"Дней с задачами на завтра: {carry}\n"
        f"\n"
        f"По дням (пн–вс):\n"
        f"{weekday_bars}\n"
        f"\n"
        f"Краткая сборка:\n"
        f"{summary}\n"
        f"\n"
        f"На следующую неделю:\n"
        f"{tips}"
    )


def parse_plus_minus(text: str) -> str:
    t = text.strip().lower().replace("−", "-").replace("–", "-")
    if t in {"+", "плюс", "да", "yes", "y", "1", "true"}:
        return "+"
    if t in {"-", "минус", "нет", "no", "n", "0", "false"}:
        return "-"
    raise ValueError("Нужен ответ + или − (можно да/нет).")


def parse_task_list(text: str) -> list[str]:
    raw = text.strip()
    if not raw:
        return []
    parts: list[str] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("•-*–— ").strip()
        if not line:
            continue
        if "," in line and "\n" not in raw:
            parts.extend(p.strip() for p in line.split(",") if p.strip())
        else:
            parts.append(line)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        key = p.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


EXAMPLE_DAILY = """🌙 Вечерний разбор · 27 октября 2026, вторник

Одно сообщение на день. После ответа править нельзя.

Сегодня планировалось —
• Созвон с отцом
• Добить бота
• Купить продукты

Ответьте по очереди на 5 вопросов:

1) Задачи на завтра (список → появятся в /tasks)
2) Чистая раковина перед отбоем (+/−)
3) Зарядка (+/−)
4) 3 полных приёма пищи (+/−)
5) Посещение группы (+/−)

Напишите ответ на вопрос 1 — список задач на завтра (с новой строки или через запятую; «нет» / «—», если задач нет)."""

EXAMPLE_WEEKLY = """📊 Итог недели · 21–27 окт 2026

Заполнено дней: 5/7
Привычки «+» (оценка): ~12
Дней с задачами на завтра: 5

По дням (пн–вс):
пн ▓▓░░ 1
вт ▓▓▓▓ 2
ср ░░░░ 0
чт ▓▓░░ 1
пт ▓▓░░ 1
сб ░░░░ 0
вс ▓▓░░ 1

Краткая сборка:
Неделя 21 окт — 27 окт 2026: 5 из 7 дней с сообщением.
Задачи на завтра оставляли в 5 днях.

На следующую неделю:
→ Стабильность записей: цель 7/7 вечерних сообщений в 22:00.
→ Раковина и зарядка — чаще «+».
→ Слабые дни: ср, сб."""
