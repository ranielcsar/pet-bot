from __future__ import annotations

from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from events.model import Event
from events import database as db
from events.tasks import setup_tasks
from events import commands as event_commands


class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.events: dict[str, Event] = {}

    async def cog_load(self):
        await db.init_db()
        self.events = await db.load_events()
        setup_tasks(self)
        self.weekly_task.start()
        self.daily_task.start()
        self.countdown_task.start()
        self.bot.tree.add_command(event_commands.register(self))

    def cog_unload(self):
        self.weekly_task.cancel()
        self.daily_task.cancel()
        self.countdown_task.cancel()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _purge_past_events(self):
        past = [eid for eid, ev in self.events.items() if ev.is_past()]
        for eid in past:
            del self.events[eid]
        if past:
            print(f"🗑️  {len(past)} evento(s) passado(s) removido(s) do cache.")

    async def _send_reminder(self, event: Event, label: Optional[str] = None):
        channel = self.bot.get_channel(event.channel_id)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(event.channel_id)
            except discord.NotFound:
                print(f"⚠️  Canal {event.channel_id} não encontrado para '{event.name}'.")
                return
        await channel.send(embed=event.reminder_embed(self.bot, label=label))

    # ── Error handler ─────────────────────────────────────────────────────────
    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ):
        msg = f"❌ Ocorreu um erro: `{error}`"
        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(msg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
