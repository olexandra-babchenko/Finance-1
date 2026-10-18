"""Atomic JSON persistence for chat sessions and completed applications."""

import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).resolve().parent / "data"
SESSIONS_FILE = DATA_DIR / "sessions.json"
APPLICATIONS_FILE = DATA_DIR / "applications.json"
_FILE_LOCK = asyncio.Lock()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _write_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_name = temporary_file.name
            json.dump(value, temporary_file, ensure_ascii=False, indent=2)
            temporary_file.write("\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


class JsonStore:
    async def get_session(self, chat_id: str) -> dict[str, Any] | None:
        async with _FILE_LOCK:
            sessions = await asyncio.to_thread(_read_json, SESSIONS_FILE, {})
            return sessions.get(chat_id)

    async def save_session(self, chat_id: str, state: dict[str, Any]) -> None:
        async with _FILE_LOCK:
            sessions = await asyncio.to_thread(_read_json, SESSIONS_FILE, {})
            sessions[chat_id] = state
            await asyncio.to_thread(_write_atomic, SESSIONS_FILE, sessions)

    async def delete_session(self, chat_id: str) -> None:
        async with _FILE_LOCK:
            sessions = await asyncio.to_thread(_read_json, SESSIONS_FILE, {})
            sessions.pop(chat_id, None)
            await asyncio.to_thread(_write_atomic, SESSIONS_FILE, sessions)

    async def save_application(self, application: dict[str, Any]) -> None:
        async with _FILE_LOCK:
            applications = await asyncio.to_thread(_read_json, APPLICATIONS_FILE, [])
            applications.append(application)
            await asyncio.to_thread(_write_atomic, APPLICATIONS_FILE, applications)
