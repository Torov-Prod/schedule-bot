# schedule-bot (Torov-Prod)

Telegram: **[@Torov_shedule_bot](https://t.me/Torov_shedule_bot)**  
Орг: [Torov-Prod](https://github.com/Torov-Prod)

Бот **Агента разбора**: каждый день в **22:00** (Europe/Moscow) три вопроса, одно сообщение в день; в **вс 18:00** — сводка недели. Команды `/tasks` и `запиши …` стыкуются с API «Календаря планов», если он доступен.

> **Важно:** long-polling нужен **процесс 24/7**. GitHub Actions (hosted runners) для этого не подходит — репозиторий публичный, рантайм на VPS / Docker-хосте / Railway / Fly.io.

## Быстрый старт (VPS)

```bash
git clone https://github.com/Torov-Prod/schedule-bot.git
cd schedule-bot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# TELEGRAM_BOT_TOKEN=…   TELEGRAM_CHAT_ID=…   TZ=Europe/Moscow
python main.py
```

В Telegram: `/start`.

### Docker

```bash
cp .env.example .env   # токены
docker build -t schedule-bot .
docker run -d --name schedule-bot --env-file .env -v schedule-bot-data:/app/data --restart unless-stopped schedule-bot
```

### systemd

```ini
# /etc/systemd/system/schedule-bot.service
[Unit]
Description=Torov schedule Telegram bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/schedule-bot
EnvironmentFile=/opt/schedule-bot/.env
ExecStart=/opt/schedule-bot/.venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

## Secrets (не коммитить)

| | |
|--|--|
| `TELEGRAM_BOT_TOKEN` | BotFather |
| `TELEGRAM_CHAT_ID` | опционально |
| `TZ` | `Europe/Moscow` |
| `CALENDAR_API_URL` / `CALENDAR_API_KEY` | если календарь рядом |

В GitHub: **Settings → Secrets and variables → Actions** — только если деплой-workflow сам копирует их на хост. В код и в Issues не класть.

## Почему не GitHub Actions как хост

`python main.py` держит long poll открытым постоянно. Hosted Actions убивает job по таймауту. CI в этом репо только проверяет синтаксис; живой бот — на отдельной машине с `--restart unless-stopped` / systemd.
