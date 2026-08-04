#!/bin/sh
# Ежедневная резервная копия базы бота.
#
# Зачем отдельный скрипт, а не `cp bot.db backups/`: бот работает в момент
# копирования, и обычное копирование файла может застать SQLite посреди
# записи — получится битая копия, о чём узнаешь только когда она понадобится.
# Поэтому копия снимается штатным механизмом SQLite (`Connection.backup`),
# который согласован с работающим ботом.
#
# Ставится в cron на сервере, см. deploy/README-deploy.md.
set -eu

PROJECT_DIR=/opt/content-bot
BACKUP_DIR="$PROJECT_DIR/backups"
KEEP=14

mkdir -p "$BACKUP_DIR"

"$PROJECT_DIR/.venv/bin/python" - "$PROJECT_DIR/bot.db" "$BACKUP_DIR" <<'PY'
import sqlite3
import sys
from datetime import date
from pathlib import Path

src, backup_dir = Path(sys.argv[1]), Path(sys.argv[2])
dst = backup_dir / f"bot-{date.today():%Y%m%d}.db"

source = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
target = sqlite3.connect(dst)
with target:
    source.backup(target)
target.close()
source.close()

print(f"{date.today():%Y-%m-%d} копия готова: {dst} ({dst.stat().st_size} байт)")
PY

# Оставляем последние KEEP копий, остальные удаляем.
ls -1t "$BACKUP_DIR"/bot-*.db 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do
    rm -f "$old"
    echo "удалена старая копия: $old"
done
