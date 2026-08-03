#!/bin/sh
# Отправляет владельцу напоминание в Telegram тем же ботом.
#
# Использование: remind-owner.sh "текст напоминания"
#
# Токен и chat id берутся из /opt/content-bot/.env, то есть нигде больше не
# дублируются. Скрипт ничего не печатает из секретов — в лог уходит только
# код ответа Telegram.
set -eu

PROJECT_DIR=/opt/content-bot
TEXT=${1:?нужен текст напоминания}

set -a
. "$PROJECT_DIR/.env"
set +a

CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    --max-time 30 \
    -X POST "https://api.telegram.org/bot$BOT_TOKEN/sendMessage" \
    --data-urlencode "chat_id=$OWNER_CHAT_ID" \
    --data-urlencode "text=$TEXT")

echo "$(date '+%Y-%m-%d %H:%M') напоминание отправлено, ответ Telegram: $CODE"
