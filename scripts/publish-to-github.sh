#!/usr/bin/env bash
# Create/push Torov-Prod/schedule-bot and set GitHub Actions secrets.
# Never prints secret values. Requires: gh + GH_TOKEN with org create/push.
set -euo pipefail

ORG="${ORG:-Torov-Prod}"
REPO_NAME="${REPO_NAME:-schedule-bot}"
FULL="$ORG/$REPO_NAME"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_DIR="${SECRETS_DIR:-/cursor/stores/self/internal/secrets}"
TELEGRAM_ENV="${TELEGRAM_ENV:-$SECRETS_DIR/telegram.env}"
CALENDAR_ENV="${CALENDAR_ENV:-$SECRETS_DIR/calendar.env}"

if [[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GH_TOKEN (or GITHUB_TOKEN) is not set."
  echo "Put a PAT in the Cloud Agent environment secret GH_TOKEN."
  echo "Classic: scope repo (+ org create-repo). Fine-grained: Torov-Prod Contents R/W + create repos."
  exit 1
fi

export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "ERROR: gh cannot authenticate with GH_TOKEN"
  gh auth status -h github.com || true
  exit 1
fi

cd "$ROOT"
if [[ ! -d .git ]]; then
  git init -b main
  git add -A
  git -c user.email="bot@torov.prod" -c user.name="Torov-Prod bot" commit -m "Initial schedule-bot for Torov-Prod"
fi

if gh repo view "$FULL" >/dev/null 2>&1; then
  echo "Repo exists: https://github.com/$FULL"
else
  echo "Creating public repo $FULL …"
  gh repo create "$FULL" --public --description "Telegram schedule / evening review bot (@Torov_shedule_bot)" --source=. --remote=origin --push
fi

# Ensure remote + push
if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "https://github.com/$FULL.git"
fi
git push -u origin HEAD:main

set_secret() {
  local name="$1" file="$2" key="$3"
  if [[ ! -f "$file" ]]; then
    echo "WARN: missing $file — skip $name"
    return 0
  fi
  # extract value without printing
  local val
  val="$(grep -E "^${key}=" "$file" | head -1 | cut -d= -f2-)"
  if [[ -z "$val" ]]; then
    echo "WARN: empty $key in $file — skip $name"
    return 0
  fi
  printf '%s' "$val" | gh secret set "$name" --repo "$FULL"
  echo "Set Actions secret: $name"
}

set_secret TELEGRAM_BOT_TOKEN "$TELEGRAM_ENV" TELEGRAM_BOT_TOKEN
set_secret TELEGRAM_CHAT_ID "$TELEGRAM_ENV" TELEGRAM_CHAT_ID
set_secret CALENDAR_API_URL "$CALENDAR_ENV" CALENDAR_API_URL
set_secret CALENDAR_API_KEY "$CALENDAR_ENV" CALENDAR_API_KEY

echo
echo "OK: https://github.com/$FULL"
echo "Next: deploy on a 24/7 host (VPS/Docker). Hosted Actions cannot keep long-poll alive."
echo "  cp .env.example .env  # fill from secrets files locally, never commit"
echo "  python main.py   # or docker run --env-file .env --restart unless-stopped"
echo "Bot: @Torov_shedule_bot → /start"
