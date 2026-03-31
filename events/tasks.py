from __future__ import annotations

import datetime
import zoneinfo

import discord
from discord.ext import tasks

from .model import Event, TIMEZONE, DAILY_FIXED

WEEKLY_REMINDER_TIME = datetime.time(9, 0, tzinfo=TIMEZONE)
DAILY_REMINDER_TIMES = [
    datetime.time(9,  0, tzinfo=TIMEZONE),
    datetime.time(13, 0, tzinfo=TIMEZONE),
    datetime.time(19, 0, tzinfo=TIMEZONE),
]


def setup_tasks(cog) -> None:
    """
    Registra as três tasks no cog recebido.
    Chamado em EventsCog.cog_load().
    """

    @tasks.loop(time=WEEKLY_REMINDER_TIME)
    async def weekly_task():
        """Lembrete semanal: às 09:00, no mesmo dia da semana do evento."""
        cog._purge_past_events()
        today_weekday = datetime.date.today().weekday()
        for event in list(cog.events.values()):
            if event.is_event_week():
                continue
            if event.weekday == today_weekday:
                await cog._send_reminder(event)

    @tasks.loop(time=DAILY_REMINDER_TIMES)
    async def daily_task():
        """Lembretes fixos (09h, 13h, 19h) na semana do evento."""
        cog._purge_past_events()
        now_time = datetime.datetime.now(tz=TIMEZONE).time().replace(second=0, microsecond=0)
        for event in list(cog.events.values()):
            if not event.is_event_week():
                continue
            if event.is_today():
                if now_time in event.daily_reminders_today():
                    await cog._send_reminder(event)
            else:
                await cog._send_reminder(event)

    @tasks.loop(minutes=1)
    async def countdown_task():
        """Lembrete '2h antes': dispara no minuto exato."""
        cog._purge_past_events()
        now = datetime.datetime.now(tz=TIMEZONE).replace(second=0, microsecond=0)
        for event in list(cog.events.values()):
            if not event.is_today():
                continue
            two_before = event.two_hours_before().replace(second=0, microsecond=0)
            if two_before <= now < two_before + datetime.timedelta(minutes=5):
                await cog._send_reminder(
                    event, label=f"⏰ 2 horas para o evento — {event.name}"
                )

    @weekly_task.before_loop
    @daily_task.before_loop
    @countdown_task.before_loop
    async def before_tasks():
        await cog.bot.wait_until_ready()

    @weekly_task.error
    @daily_task.error
    @countdown_task.error
    async def task_error(error: Exception):
        print(f"❌ Erro numa task de lembrete: {error}")

    # Anexa as tasks ao cog para poder iniciar/cancelar
    cog.weekly_task   = weekly_task
    cog.daily_task    = daily_task
    cog.countdown_task = countdown_task
