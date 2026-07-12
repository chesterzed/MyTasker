#!/usr/bin/env bash
#
# scripts/install.sh
#
# Регистрирует MyTasker как пользовательскую службу macOS (LaunchAgent) и
# запускает её. Процесс оборачивается в caffeinate, чтобы Mac не засыпал,
# пока бот работает. Служба стартует при входе в систему (RunAtLoad) и
# автоматически перезапускается при падении/перезагрузке (KeepAlive).
#
# Запуск:  ./scripts/install.sh
#
set -euo pipefail

LABEL="com.mytasker.bot"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$PROJECT_DIR/venv/bin/python3"
ENTRY="$PROJECT_DIR/run_bot.py"
UID_NUM="$(id -u)"

# --- Проверки окружения ------------------------------------------------------
if [ ! -x "$PY" ]; then
    echo "ОШИБКА: не найден интерпретатор venv: $PY" >&2
    echo "Создайте окружение и установите зависимости:" >&2
    echo "    cd \"$PROJECT_DIR\"" >&2
    echo "    python3 -m venv venv && ./venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi
if [ ! -f "$ENTRY" ]; then
    echo "ОШИБКА: не найдена точка входа: $ENTRY" >&2
    exit 1
fi

mkdir -p "$PROJECT_DIR/logs" "$HOME/Library/LaunchAgents"

# --- Идемпотентная переустановка: снимаем старую версию, если загружена -------
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true

# --- Пишем plist -------------------------------------------------------------
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-i</string>
        <string>-s</string>
        <string>$PY</string>
        <string>$ENTRY</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$PROJECT_DIR</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>

    <key>StandardOutPath</key>
    <string>$PROJECT_DIR/logs/bot.out.log</string>
    <key>StandardErrorPath</key>
    <string>$PROJECT_DIR/logs/bot.err.log</string>
</dict>
</plist>
PLIST_EOF

# --- Загружаем и запускаем ----------------------------------------------------
# bootstrap — актуальный способ (macOS 11+); load -w — запасной для совместимости.
if ! launchctl bootstrap "gui/$UID_NUM" "$PLIST" 2>/dev/null; then
    launchctl load -w "$PLIST"
fi

echo "Служба '$LABEL' установлена и запущена."
echo "  plist:  $PLIST"
echo "  логи:   $PROJECT_DIR/logs/bot.err.log"
echo
echo "Статус:"
launchctl list | grep "$LABEL" || echo "  (пока не в списке — проверьте логи)"
echo
echo "Смотреть лог:   tail -f \"$PROJECT_DIR/logs/bot.err.log\""
echo "Остановить/удалить:  ./scripts/uninstall.sh"
