from __future__ import annotations

import os
import aiosqlite

from .model import Event

os.makedirs("data", exist_ok=True)
DB_PATH = "data/events.db"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                date        TEXT NOT NULL,
                time        TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                channel_id  INTEGER NOT NULL,
                created_by  INTEGER NOT NULL
            )
        """)
        await db.commit()


async def load_events() -> dict[str, Event]:
    """Carrega eventos futuros do banco e retorna o cache."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT * FROM events") as cursor:
            rows = await cursor.fetchall()

    cache: dict[str, Event] = {}
    for row in rows:
        event = Event.from_row(row)
        if not event.is_past():
            cache[event.id] = event

    print(f"📦 {len(cache)} evento(s) carregado(s) do banco.")
    return cache


async def save_event(event: Event) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
            event.to_row(),
        )
        await db.commit()


async def delete_event(event_id: str) -> None:
    """Remove do banco (eventos passados ficam para relatórios)."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
        await db.commit()


async def update_event(event: Event) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE events SET name=?, date=?, time=?, description=?, channel_id=? WHERE id=?",
            (
                event.name,
                event.date.isoformat(),
                event.time.strftime("%H:%M"),
                event.description,
                event.channel_id,
                event.id,
            ),
        )
        await db.commit()
