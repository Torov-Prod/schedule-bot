"""
Агент разбора — Telegram-бот.

Расписание (Europe/Moscow по умолчанию):
  • каждый день 22:00 — вопросы дня
  • воскресенье 18:00 — сводка и статистика за неделю (Пн–Вс)

Запуск:
  cd bot && python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env   # вписать TELEGRAM_BOT_TOKEN
  python main.py
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

import calendar_client as cal
from messages import (
    EXAMPLE_DAILY,
    EXAMPLE_WEEKLY,
    QUESTION_FIELDS,
    QUESTION_KINDS,
    QUESTIONS,
    already_saved,
    ask_question,
    daily_prompt,
    daily_saved,
    parse_plus_minus,
    parse_task_list,
    weekly_stats_message,
)
from storage import Store
from weekly import (
    build_weekly,
    date_key,
    format_date_ru,
    now_tz,
    week_bounds,
    week_label,
)

ROOT = Path(__file__).resolve().parent
# Standalone package: .env next to main.py (optional parent .env for monorepo)
load_dotenv(ROOT.parent / ".env")
load_dotenv(ROOT / ".env", override=True)

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID_ENV = os.getenv("TELEGRAM_CHAT_ID", "").strip()
TZ_NAME = os.getenv("TZ", "Europe/Moscow")
DATA_PATH = Path(os.getenv("DATA_PATH", str(ROOT / "data" / "store.json")))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("agent-razbora-bot")

def resolve_chat_id(store: Store) -> int | None:
    if CHAT_ID_ENV:
        return int(CHAT_ID_ENV)
    return store.chat_id


def planned_from_yesterday(store: Store, today_key: str) -> list[str]:
    prev = store.previous_entry(today_key)
    if not prev:
        return []
    return parse_task_list(prev.get("answers", {}).get("tasksTomorrow", "") or "")


async def push_tomorrow_tasks(
    tasks: list[str], *, chat_id: int | str, tomorrow: str
) -> int:
    """Создать планы в календаре на завтра → видны в /tasks."""
    n = 0
    for title in tasks:
        try:
            await asyncio.to_thread(
                cal.create_plan,
                title=title,
                date=tomorrow,
                time=None,
                notes="из вечернего разбора",
                chat_id=str(chat_id),
                notify=False,
            )
            n += 1
        except Exception as e:
            log.warning("не удалось создать задачу «%s»: %s", title, e)
    return n


async def send_daily_prompt(bot: Bot, store: Store) -> None:
    chat_id = resolve_chat_id(store)
    if not chat_id:
        log.warning("Нет chat_id — пропуск вечернего сообщения (/start не был)")
        return

    today = now_tz(TZ_NAME).date()
    key = date_key(today)
    label = format_date_ru(today)

    if store.entry_for(key):
        await bot.send_message(chat_id, already_saved(label))
        return

    store.start_pending(key)
    planned = planned_from_yesterday(store, key)
    await bot.send_message(chat_id, daily_prompt(label, planned))


async def send_weekly_stats(bot: Bot, store: Store) -> None:
    chat_id = resolve_chat_id(store)
    if not chat_id:
        log.warning("Нет chat_id — пропуск недельной сводки")
        return

    today = now_tz(TZ_NAME).date()
    start, end = week_bounds(today)
    if store.weekly_for(date_key(start)):
        log.info("Итог недели уже есть — не дублируем")
        return

    review = build_weekly(store.all_entries(), start, end)
    store.add_weekly({k: v for k, v in review.items() if not k.startswith("_")})

    text = weekly_stats_message(
        week_label=week_label(start, end),
        days_filled=review["daysFilled"],
        tasks_done=review["_tasks_done"],
        carry=review["_carry"],
        weekday_bars=review["_weekday_bars"],
        summary=review["summaryText"],
        suggestions=review["_suggestion_lines"],
    )
    await bot.send_message(chat_id, text)


def setup_scheduler(bot: Bot, store: Store) -> AsyncIOScheduler:
    tz = ZoneInfo(TZ_NAME)
    sched = AsyncIOScheduler(timezone=tz)
    evening_h = int(store._data["settings"]["eveningHour"])
    evening_m = int(store._data["settings"]["eveningMinute"])
    weekly_h = int(store._data["settings"]["weeklyHour"])
    weekly_m = int(store._data["settings"]["weeklyMinute"])

    sched.add_job(
        send_daily_prompt,
        CronTrigger(hour=evening_h, minute=evening_m, timezone=tz),
        args=[bot, store],
        id="daily_22",
        replace_existing=True,
    )
    sched.add_job(
        send_weekly_stats,
        CronTrigger(day_of_week="sun", hour=weekly_h, minute=weekly_m, timezone=tz),
        args=[bot, store],
        id="weekly_sun_18",
        replace_existing=True,
    )
    return sched


async def main() -> None:
    if not TOKEN:
        print("Нет TELEGRAM_BOT_TOKEN — бот в idle (календарь/API работают).")
        print("Заполните TELEGRAM_BOT_TOKEN в корневом .env и перезапустите.")
        print("\n--- Пример вечернего сообщения ---\n")
        print(EXAMPLE_DAILY)
        print("\n--- Пример статистики за неделю ---\n")
        print(EXAMPLE_WEEKLY)
        # Stay alive so `npm start` keeps the stack (calendar) running.
        while True:
            await asyncio.sleep(3600)

    store = Store(DATA_PATH)
    bot = Bot(TOKEN)
    dp = Dispatcher()
    sched = setup_scheduler(bot, store)

    @dp.message(CommandStart())
    async def on_start(message: Message) -> None:
        store.set_chat_id(message.chat.id)
        await message.answer(
            "Агент разбора на связи.\n\n"
            "Каждый день в 22:00 пришлю три вопроса.\n"
            "В воскресенье в 18:00 — сводку и статистику за неделю (Пн–Вс).\n\n"
            "Команды:\n"
            "/tasks — задачи / расписание на сегодня\n"
            "/tasks 28.10 — расписание на дату\n"
            "/today — начать разбор сейчас\n"
            "/week — собрать итог недели сейчас\n"
            "/status — есть ли запись за сегодня\n"
            "/examples — примеры сообщений бота\n\n"
            "Добавить план в календарь:\n"
            "запиши завтра встреча с отцом на 15, напомни в 13:20"
        )

    @dp.message(Command("tasks", "schedule"))
    async def on_tasks(message: Message) -> None:
        store.set_chat_id(message.chat.id)
        today = now_tz(TZ_NAME).date()
        arg = ""
        if message.text:
            parts = message.text.split(maxsplit=1)
            arg = parts[1].strip() if len(parts) > 1 else ""

        try:
            if arg:
                day = cal.normalize_date(arg, default_year=today.year)
            else:
                day = date_key(today)
        except ValueError as e:
            await message.answer(f"Не понял дату. Пример: /tasks 28.10\n{e}")
            return

        plans = await asyncio.to_thread(cal.list_plans, day)
        from datetime import date as date_cls

        try:
            label = format_date_ru(date_cls.fromisoformat(day))
        except ValueError:
            label = day

        via = "API календаря" if await asyncio.to_thread(cal.api_available) else "общий файл календаря"
        text = cal.format_plans(plans, f"📋 Задачи на {label}\n({via})")
        await message.answer(text)

    @dp.message(Command("examples"))
    async def on_examples(message: Message) -> None:
        await message.answer(EXAMPLE_DAILY)
        await message.answer(EXAMPLE_WEEKLY)

    @dp.message(Command("status"))
    async def on_status(message: Message) -> None:
        store.set_chat_id(message.chat.id)
        today = now_tz(TZ_NAME).date()
        entry = store.entry_for(date_key(today))
        if entry:
            a = entry["answers"]
            await message.answer(
                f"Сегодня уже записано.\n"
                f"• Задачи на завтра:\n{a.get('tasksTomorrow') or '—'}\n"
                f"• Раковина {a.get('sinkClean', '—')} · "
                f"Зарядка {a.get('exercise', '—')} · "
                f"Еда {a.get('threeMeals', '—')} · "
                f"Группа {a.get('groupVisit', '—')}"
            )
        else:
            pending = store.pending()
            if pending and pending.get("date") == date_key(today):
                await message.answer(
                    f"Идёт разбор: шаг {pending['step'] + 1}/3 — {QUESTIONS[pending['step']]}"
                )
            else:
                await message.answer("За сегодня ещё нет сообщения. /today или ждите 22:00.")

    @dp.message(Command("today"))
    async def on_today(message: Message) -> None:
        store.set_chat_id(message.chat.id)
        await send_daily_prompt(bot, store)

    @dp.message(Command("week"))
    async def on_week(message: Message) -> None:
        store.set_chat_id(message.chat.id)
        # force: удалим флаг «уже есть», если пользователь явно просит — только если нет
        today = now_tz(TZ_NAME).date()
        start, _ = week_bounds(today)
        if store.weekly_for(date_key(start)):
            await message.answer("Итог этой недели уже собран. Пришлю копию.")
            review = store.weekly_for(date_key(start))
            assert review is not None
            # пересоберём текст из текущих entries для актуальности баров
            rebuilt = build_weekly(store.all_entries(), *week_bounds(today))
            text = weekly_stats_message(
                week_label=week_label(*week_bounds(today)),
                days_filled=rebuilt["daysFilled"],
                tasks_done=rebuilt["_tasks_done"],
                carry=rebuilt["_carry"],
                weekday_bars=rebuilt["_weekday_bars"],
                summary=rebuilt["summaryText"],
                suggestions=rebuilt["_suggestion_lines"],
            )
            await message.answer(text)
            return
        await send_weekly_stats(bot, store)

    @dp.message(F.text.regexp(r"(?i)^(запиши(?:\s+план)?|add)\s+"))
    async def on_add_plan(message: Message) -> None:
        store.set_chat_id(message.chat.id)
        today = now_tz(TZ_NAME).date()
        assert message.text
        try:
            parsed = cal.parse_add_command(message.text, default_year=today.year)
        except ValueError as e:
            await message.answer(str(e))
            return

        plan, channel = await asyncio.to_thread(
            cal.create_plan,
            title=str(parsed["title"]),
            date=str(parsed["date"]),
            time=parsed.get("time"),
            notes=parsed.get("notes"),
            remind_date=parsed.get("remindDate"),
            remind_time=parsed.get("remindTime"),
            chat_id=str(message.chat.id),
            notify=False,
        )
        where = (
            "календарь (HTTP API)"
            if channel == "http"
            else "общий файл — календарь подхватит при синхронизации"
        )
        when = f"{plan.date}" + (f" {plan.time}" if plan.time else "")
        await message.answer(
            f"✅ План добавлен ({where})\n"
            f"• {plan.title}\n"
            f"• {when}\n"
            + (f"• {plan.notes}\n" if plan.notes else "")
            + f"id: `{plan.id}`"
        )

    @dp.message(F.text)
    async def on_text(message: Message) -> None:
        if not message.text or message.text.startswith("/"):
            return
        store.set_chat_id(message.chat.id)
        today = now_tz(TZ_NAME).date()
        key = date_key(today)
        label = format_date_ru(today)

        pending = store.pending()
        if not pending or pending.get("date") != key:
            if store.entry_for(key):
                await message.answer(
                    already_saved(label)
                    + "\n\nИли: /tasks · запиши завтра встреча на 15, напомни в 13:20"
                )
            else:
                await message.answer(
                    "Сейчас не жду ответ на разбор.\n"
                    "/today — вечерний разбор\n"
                    "/tasks — задачи на сегодня\n"
                    "запиши завтра встреча с отцом на 15, напомни в 13:20"
                )
            return

        if store.entry_for(key):
            await message.answer(already_saved(label))
            return

        step = int(pending["step"])
        if step >= len(QUESTION_FIELDS):
            store.clear_pending()
            await message.answer("Что-то пошло не так со шагом. Напишите /today ещё раз.")
            return

        field = QUESTION_FIELDS[step]
        kind = QUESTION_KINDS[step]
        raw = message.text.strip()

        try:
            if kind == "pm":
                value = parse_plus_minus(raw)
            elif kind == "tasks":
                if raw.lower() in {"нет", "нету", "-", "—", "–", "ничего"}:
                    value = ""
                else:
                    tasks = parse_task_list(raw)
                    if not tasks:
                        await message.answer(
                            "Нужен список задач (с новой строки или через запятую),\n"
                            "или «нет» / «—», если задач нет."
                        )
                        return
                    value = "\n".join(tasks)
            else:
                value = raw
        except ValueError as e:
            await message.answer(str(e))
            return

        pending = store.update_pending_answer(field, value)

        if pending["step"] >= len(QUESTION_FIELDS):
            entry = store.commit_pending()
            # задачи на завтра → календарь /tasks
            tasks = parse_task_list(entry["answers"].get("tasksTomorrow", ""))
            if tasks:
                from datetime import timedelta

                tomorrow = (today + timedelta(days=1)).isoformat()
                n = await push_tomorrow_tasks(
                    tasks, chat_id=message.chat.id, tomorrow=tomorrow
                )
                await message.answer(daily_saved(label, entry["answers"]))
                if n:
                    await message.answer(
                        f"📋 В календарь на завтра добавлено задач: {n}. Смотрите /tasks завтра."
                    )
            else:
                await message.answer(daily_saved(label, entry["answers"]))
            return

        await message.answer(ask_question(pending["step"]))

    sched.start()
    log.info(
        "Бот запущен. TZ=%s daily=%s:%02d weekly=Sun %s:%02d",
        TZ_NAME,
        store._data["settings"]["eveningHour"],
        store._data["settings"]["eveningMinute"],
        store._data["settings"]["weeklyHour"],
        store._data["settings"]["weeklyMinute"],
    )
    try:
        await dp.start_polling(bot)
    finally:
        sched.shutdown(wait=False)
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
