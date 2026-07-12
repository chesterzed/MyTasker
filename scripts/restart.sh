#!/usr/bin/env bash
#
# scripts/restart.sh
#
# Перезапускает службу MyTasker (LaunchAgent): гасит текущий процесс и
# поднимает заново. Удобно после git pull / правок кода.
#
# Запуск:  ./scripts/restart.sh
#
set -euo pipefail

LABEL="com.mytasker.bot"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

if [ ! -f "$PLIST" ]; then
    echo "ОШИБКА: служба не установлена ($PLIST не найден)." >&2
    echo "Сначала установите её: ./scripts/install.sh" >&2
    exit 1
fi

# kickstart -k: если процесс запущен — убить и запустить снова; если нет — просто запустить.
# Запасной путь (unload+load) — на случай, если служба выгружена из launchd.
if ! launchctl kickstart -k "gui/$UID_NUM/$LABEL" 2>/dev/null; then
    launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
    launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null \
        || launchctl load -w "$PLIST"
fi

echo "Служба '$LABEL' перезапущена."
echo
echo "Статус:"
launchctl list | grep "$LABEL" || echo "  (пока не в списке — проверьте логи)"
