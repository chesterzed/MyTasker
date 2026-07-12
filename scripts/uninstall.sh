#!/usr/bin/env bash
#
# scripts/uninstall.sh
#
# Останавливает службу MyTasker (LaunchAgent) и удаляет её plist.
# Логи в logs/ намеренно НЕ трогаются.
#
# Запуск:  ./scripts/uninstall.sh
#
set -euo pipefail

LABEL="com.mytasker.bot"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

# --- Останавливаем и снимаем регистрацию (терпим "не загружена") --------------
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null \
    || launchctl unload -w "$PLIST" 2>/dev/null \
    || true

# --- Удаляем plist ------------------------------------------------------------
rm -f "$PLIST"

echo "Служба '$LABEL' остановлена и удалена."
echo "  plist удалён: $PLIST"
echo "  логи оставлены: $PROJECT_DIR/logs/ (удалить вручную: rm -rf \"$PROJECT_DIR/logs\")"
