"""
scripts/rollover_pending.py

Разовая правка данных: подтягивает «вторую» (активную) дату всех просроченных
незакрытых задач на сегодня — то же, что делает ночной джоб в 00:01, но прямо
сейчас и для всех пользователей. Полезно для задач, созданных до появления
переноса: их активная дата осталась в прошлом, поэтому они не попадали в /today.

Будущие задачи и уже закрытые не трогаются; каждый пользователь считается в
своём часовом поясе.

Запуск из корня проекта:
    python scripts/rollover_pending.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from bot.services import repository as repo  # noqa: E402
from bot.utils import today_local  # noqa: E402


def main() -> None:
    users = repo.get_all_users()
    total = 0
    for user in users:
        today = today_local(user)
        moved = repo.roll_over_tasks(user["id"], today)
        total += moved
        print(
            f"user {user['id']} (tz={user['timezone'] or 'UTC'}, today={today}): "
            f"перенесено {moved}"
        )
    print(f"Итого перенесено задач: {total} (пользователей: {len(users)})")


if __name__ == "__main__":
    main()
