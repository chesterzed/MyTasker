"""
bot/handlers/__init__.py

Порядок включения роутеров критичен: catch-all свободного текста (ai_chat)
должен идти последним, иначе он перехватит команды и FSM-ответы.
"""
from aiogram import Router


def build_root_router() -> Router:
    from bot.handlers import addaim, ai_chat, commands, proposals, setkey, tasks, voice

    root = Router(name="root")
    root.include_router(commands.router)
    root.include_router(addaim.router)
    root.include_router(setkey.router)
    root.include_router(proposals.router)
    root.include_router(tasks.router)
    root.include_router(voice.router)     # перед ai_chat: F.voice не пересекается с F.text
    root.include_router(ai_chat.router)   # строго последним
    return root
