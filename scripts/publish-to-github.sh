#!/usr/bin/env bash
# Push bot-only package to Torov-Prod/<repo> and set Actions secrets.
# Never prints secret values. Requires GH_TOKEN.
#
# Env:
#   REPO_NAME   default schedule-bot (try torov-schedule-bot if taken)
#   ORG/USER    default Torov-Prod (this account is a User, not an org)
#   PUSH_ONLY=1 skip create; fail if repo missing
set -euo pipefail

OWNER="${OWNER:-Torov-Prod}"
REPO_NAME="${REPO_NAME:-schedule-bot}"
FULL="$OWNER/$REPO_NAME"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SECRETS_DIR="${SECRETS_DIR:-/cursor/stores/self/internal/secrets}"
TELEGRAM_ENV="${TELEGRAM_ENV:-$SECRETS_DIR/telegram.env}"
CALENDAR_ENV="${CALENDAR_ENV:-$SECRETS_DIR/calendar.env}"
TOKEN_FILE="${TOKEN_FILE:-$SECRETS_DIR/gh_token.env}"
PUSH_ONLY="${PUSH_ONLY:-0}"

if [[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]]; then
  if [[ -f "$TOKEN_FILE" ]]; then
    GH_TOKEN="$(tr -d '\r\n' < "$TOKEN_FILE")"
    export GH_TOKEN
  fi
fi
if [[ -z "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]]; then
  echo "ERROR: GH_TOKEN not set and $TOKEN_FILE missing"
  exit 1
fi
export GH_TOKEN="${GH_TOKEN:-$GITHUB_TOKEN}"

if ! gh auth status -h github.com >/dev/null 2>&1; then
  echo "ERROR: gh cannot authenticate with GH_TOKEN"
  exit 1
fi

cd "$ROOT"
if [[ ! -d .git ]]; then
  git init -b main
  git add -A
  git -c user.email="bot@torov.prod" -c user.name="Torov-Prod bot" \
    commit -m "Initial schedule-bot for Torov-Prod"
fi

ensure_remote() {
  local url="https://github.com/$FULL.git"
  if git remote get-url origin >/dev/null 2>&1; then
    git remote set-url origin "$url"
  else
    git remote add origin "$url"
  fi
}

if gh repo view "$FULL" >/dev/null 2>&1; then
  echo "Repo exists: https://github.com/$FULL"
  ensure_remote
  git push -u origin HEAD:main
else
  if [[ "$PUSH_ONLY" == "1" ]]; then
    echo "ERROR: https://github.com/$FULL missing and PUSH_ONLY=1"
    echo "Create an empty PUBLIC repo in the GitHub UI, then re-run."
    exit 1
  fi
  echo "Creating public repo $FULL …"
  if ! gh repo create "$FULL" --public \
      --description "Telegram schedule / evening review bot (@Torov_shedule_bot)" \
      --source=. --remote=origin --push; then
    echo
    echo "CREATE FAILED (fine-grained PAT often lacks createRepository)."
    echo "Fix one of:"
    echo "  A) GitHub UI → New repository → PUBLIC empty → https://github.com/$FULL"
    echo "     then: PUSH_ONLY=1 bash $0"
    echo "  B) Replace gh_token.env with a classic PAT that has public_repo (or repo) scope"
    exit 1
  fi
fi

set_secret() {
  local name="$1" file="$2" key="$3"
  if [[ ! -f "$file" ]]; then
    echo "WARN: missing $file — skip $name"
    return 0
  fi
  local val
  val="$(grep -E "^${key}=" "$file" | head -1 | cut -d= -f2-)"
  if [[ -z "$val" ]]; then
    echo "WARN: empty $key — skip $name"
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
echo "NOTE: Hosted GitHub Actions cannot keep Telegram long-poll 24/7."
echo "Deploy on VPS/Docker: see README. Bot @Torov_shedule_bot → /start"
