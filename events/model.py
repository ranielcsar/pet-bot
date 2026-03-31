from __future__ import annotations

import datetime
import zoneinfo
from dataclasses import dataclass
from typing import Optional

import discord
from discord.ext import commands

TIMEZONE = zoneinfo.ZoneInfo("America/Sao_Paulo")

DAILY_FIXED = [
    datetime.time(9,  0),
    datetime.time(13, 0),
    datetime.time(19, 0),
]


@dataclass
class Event:
    id: str
    name: str
    date: datetime.date
    time: datetime.time
    description: str
    channel_id: int
    created_by: int

    @property
    def weekday(self) -> int:
        return self.date.weekday()

    def is_past(self) -> bool:
        event_dt = datetime.datetime.combine(self.date, self.time, tzinfo=TIMEZONE)
        return event_dt < datetime.datetime.now(tz=TIMEZONE)

    def days_until(self) -> int:
        return (self.date - datetime.date.today()).days

    def is_event_week(self) -> bool:
        today      = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())
        week_end   = week_start + datetime.timedelta(days=6)
        return week_start <= self.date <= week_end

    def is_today(self) -> bool:
        return self.date == datetime.date.today()

    def formatted_datetime(self) -> str:
        return f"{self.date.strftime('%d/%m/%Y')} às {self.time.strftime('%H:%M')}"

    def daily_reminders_today(self) -> list[datetime.time]:
        """
        Horários fixos permitidos no dia do evento.
        O último fixo que caberia é removido — substituído pelo '2h antes'.
        """
        before = [t for t in DAILY_FIXED if t < self.time]
        if not before:
            return []
        before.pop()
        return before

    def two_hours_before(self) -> datetime.datetime:
        event_dt = datetime.datetime.combine(self.date, self.time, tzinfo=TIMEZONE)
        return event_dt - datetime.timedelta(hours=2)

    def reminder_embed(self, bot: commands.Bot, label: Optional[str] = None) -> discord.Embed:
        days = self.days_until()
        if days == 0:
            when, color = "**HOJE!** 🎉", discord.Color.red()
        elif days == 1:
            when, color = "**AMANHÃ!** ⚠️", discord.Color.orange()
        elif days <= 7:
            when, color = f"em **{days} dias** 📅", discord.Color.yellow()
        else:
            when, color = f"em **{days} dias**", discord.Color.blurple()

        embed = discord.Embed(
            title=label or f"🔔 Lembrete — {self.name}",
            description=self.description,
            color=color,
        )
        embed.add_field(name="🗓 Data", value=self.formatted_datetime(), inline=True)
        if days <= 1:
            embed.add_field(name=when, value="\u200b", inline=True)
        else:
            embed.add_field(name="⏳ Falta", value=when, inline=True)
        embed.set_footer(text=f"ID do evento: {self.id}")
        return embed

    # ── Serialização ──────────────────────────────────────────────────────────
    def to_row(self) -> tuple:
        return (
            self.id,
            self.name,
            self.date.isoformat(),
            self.time.strftime("%H:%M"),
            self.description,
            self.channel_id,
            self.created_by,
        )

    @classmethod
    def from_row(cls, row: tuple) -> "Event":
        id_, name, date_str, time_str, desc, channel_id, created_by = row
        return cls(
            id=id_,
            name=name,
            date=datetime.date.fromisoformat(date_str),
            time=datetime.datetime.strptime(time_str, "%H:%M").time(),
            description=desc,
            channel_id=channel_id,
            created_by=created_by,
        )
