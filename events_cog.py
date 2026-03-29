"""
events_cog.py — Cog de gerenciamento de eventos com lembretes automáticos.

Regras de lembrete:
  • Fora da semana do evento  → 1 lembrete semanal (mesmo dia da semana, às 09:00)
  • Na semana do evento       → lembretes diários às 08:00, 14:00 e 20:00
  • No dia do evento:
      - Os lembretes fixos só são enviados SE forem antes do evento
      - O último lembrete fixo que caberia é SUBSTITUÍDO pelo "2h antes"
      - Se nenhum lembrete fixo couber (evento antes das 10h), apenas o semanal roda
  • Após o evento             → removido do cache (mantido no banco para relatórios)

Armazenamento: SQLite via aiosqlite (arquivo events.db).
"""

from __future__ import annotations

import uuid
import re
import datetime
import zoneinfo
from dataclasses import dataclass
from typing import Optional

import discord
import aiosqlite
from discord import app_commands
from discord.ext import commands, tasks


# ── Configuração ──────────────────────────────────────────────────────────────
TIMEZONE             = zoneinfo.ZoneInfo("America/Sao_Paulo")
DB_PATH              = "events.db"

DAILY_REMINDER_TIMES = [
    datetime.time(8,  0, tzinfo=TIMEZONE),
    datetime.time(14, 0, tzinfo=TIMEZONE),
    datetime.time(20, 0, tzinfo=TIMEZONE),
]
WEEKLY_REMINDER_TIME = datetime.time(9, 0, tzinfo=TIMEZONE)

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


# ── Modelo de dados ───────────────────────────────────────────────────────────
@dataclass
class Event:
    id: str
    name: str
    date: datetime.date
    time: datetime.time          # obrigatório
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
        fixed  = [datetime.time(8, 0), datetime.time(14, 0), datetime.time(20, 0)]
        before = [t for t in fixed if t < self.time]
        if not before:
            return []       # evento antes das 10h: nenhum fixo cabe
        before.pop()        # remove o último (cedido ao "2h antes")
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
        embed.add_field(name="📆 Data",  value=self.formatted_datetime(), inline=True)
        embed.add_field(name="⏳ Falta", value=when,                      inline=True)
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


# ── Cog ───────────────────────────────────────────────────────────────────────
class EventsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.events: dict[str, Event] = {}   # cache em memória

    async def cog_load(self):
        await self._init_db()
        await self._load_events()
        self.weekly_task.start()
        self.daily_task.start()
        self.countdown_task.start()

    def cog_unload(self):
        self.weekly_task.cancel()
        self.daily_task.cancel()
        self.countdown_task.cancel()

    # ── Banco de dados ────────────────────────────────────────────────────────

    async def _init_db(self):
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

    async def _load_events(self):
        """Carrega eventos futuros do banco para o cache."""
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT * FROM events") as cursor:
                rows = await cursor.fetchall()
        for row in rows:
            event = Event.from_row(row)
            if not event.is_past():
                self.events[event.id] = event
        print(f"📦 {len(self.events)} evento(s) carregado(s) do banco.")

    async def _save_event(self, event: Event):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)", event.to_row())
            await db.commit()

    async def _delete_event_db(self, event_id: str):
        """Remove do banco (usado apenas no /evento remover — eventos passados ficam)."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM events WHERE id = ?", (event_id,))
            await db.commit()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _purge_past_events(self):
        """Remove eventos passados do cache; o registro permanece no banco."""
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
        await channel.send(content="@everyone", embed=event.reminder_embed(self.bot, label=label))

    # ── Tasks ─────────────────────────────────────────────────────────────────

    @tasks.loop(time=WEEKLY_REMINDER_TIME)
    async def weekly_task(self):
        """Lembrete semanal: às 09:00, no mesmo dia da semana do evento."""
        self._purge_past_events()
        today_weekday = datetime.date.today().weekday()
        for event in list(self.events.values()):
            if event.is_event_week():
                continue
            if event.weekday == today_weekday:
                await self._send_reminder(event)

    @tasks.loop(time=DAILY_REMINDER_TIMES)
    async def daily_task(self):
        """Lembretes fixos (08h, 14h, 20h) na semana do evento."""
        self._purge_past_events()
        now_time = datetime.datetime.now(tz=TIMEZONE).time().replace(second=0, microsecond=0)
        for event in list(self.events.values()):
            if not event.is_event_week():
                continue
            if event.is_today():
                if now_time in event.daily_reminders_today():
                    await self._send_reminder(event)
            else:
                await self._send_reminder(event)

    @tasks.loop(minutes=1)
    async def countdown_task(self):
        """Lembrete '2h antes': dispara no minuto exato."""
        self._purge_past_events()
        now = datetime.datetime.now(tz=TIMEZONE).replace(second=0, microsecond=0)
        for event in list(self.events.values()):
            if not event.is_today():
                continue
            two_before = event.two_hours_before().replace(second=0, microsecond=0)
            if now == two_before:
                await self._send_reminder(event, label=f"⏰ 2 horas para o evento — {event.name}")

    @weekly_task.before_loop
    @daily_task.before_loop
    @countdown_task.before_loop
    async def before_tasks(self):
        await self.bot.wait_until_ready()

    @weekly_task.error
    @daily_task.error
    @countdown_task.error
    async def task_error(self, error: Exception):
        print(f"❌ Erro numa task de lembrete: {error}")

    # ── Slash Commands ────────────────────────────────────────────────────────

    evento_group = app_commands.Group(
        name="evento",
        description="Gerenciamento de eventos com lembretes automáticos.",
    )

    @evento_group.command(name="adicionar", description="Registra um novo evento para ser lembrado.")
    @app_commands.describe(
        nome="Nome do evento",
        data="Data no formato DD/MM/AAAA (ex: 30/03/2026)",
        horario="Horário no formato HH:MM (ex: 14:30)",
        descricao="Descrição do evento",
        canal="Canal onde os lembretes serão enviados",
    )
    async def evento_adicionar(
        self,
        interaction: discord.Interaction,
        nome: str,
        data: str,
        horario: str,
        descricao: str,
        canal: discord.TextChannel,
    ):
        if not DATE_PATTERN.match(data.strip()):
            await interaction.response.send_message(
                "❌ Formato de data inválido. Use **DD/MM/AAAA** — ex: `30/03/2026`",
                ephemeral=True,
            )
            return
        try:
            event_date = datetime.datetime.strptime(data.strip(), "%d/%m/%Y").date()
        except ValueError:
            await interaction.response.send_message(
                "❌ Data inválida (dia ou mês fora do intervalo). Ex: `30/03/2026`",
                ephemeral=True,
            )
            return

        if not TIME_PATTERN.match(horario.strip()):
            await interaction.response.send_message(
                "❌ Formato de horário inválido. Use **HH:MM** — ex: `14:30`",
                ephemeral=True,
            )
            return
        try:
            event_time = datetime.datetime.strptime(horario.strip(), "%H:%M").time()
        except ValueError:
            await interaction.response.send_message(
                "❌ Horário inválido. Ex: `14:30`", ephemeral=True,
            )
            return

        event_dt = datetime.datetime.combine(event_date, event_time, tzinfo=TIMEZONE)
        if event_dt <= datetime.datetime.now(tz=TIMEZONE):
            await interaction.response.send_message(
                "❌ O evento já passou! Informe uma data e horário futuros.",
                ephemeral=True,
            )
            return

        event_id = str(uuid.uuid4())[:8]
        event = Event(
            id=event_id,
            name=nome,
            date=event_date,
            time=event_time,
            description=descricao,
            channel_id=canal.id,
            created_by=interaction.user.id,
        )
        await self._save_event(event)
        self.events[event_id] = event

        fixos     = event.daily_reminders_today() if event.is_today() else [
                        datetime.time(8, 0), datetime.time(14, 0), datetime.time(20, 0)]
        fixos_str = ", ".join(t.strftime("%H:%M") for t in fixos) if fixos else "nenhum"
        dois_antes = event.two_hours_before().strftime("%H:%M")

        embed = discord.Embed(title="✅ Evento registrado!", color=discord.Color.green())
        embed.add_field(name="📌 Nome",   value=nome,                         inline=False)
        embed.add_field(name="📆 Data",   value=event.formatted_datetime(),   inline=True)
        embed.add_field(name="⏳ Faltam", value=f"{event.days_until()} dias", inline=True)
        embed.add_field(name="📣 Canal",  value=canal.mention,                inline=True)
        embed.add_field(
            name="🔔 Lembretes",
            value=(
                f"• **Semanal** — toda semana no mesmo dia às 09:00\n"
                f"• **Diário** — na semana do evento: {fixos_str}\n"
                f"• **2h antes** — no dia do evento às {dois_antes}"
            ),
            inline=False,
        )
        embed.set_footer(text=f"ID: {event_id} • Use /evento listar para ver todos.")
        await interaction.response.send_message(embed=embed)

    @evento_group.command(name="listar", description="Lista todos os eventos registrados.")
    async def evento_listar(self, interaction: discord.Interaction):
        self._purge_past_events()
        if not self.events:
            await interaction.response.send_message(
                "📭 Nenhum evento registrado. Use `/evento adicionar` para criar um.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(title="📅 Eventos Registrados", color=discord.Color.blurple())
        for ev in sorted(self.events.values(), key=lambda e: (e.date, e.time)):
            semana_label = " 🚨 **(ESTA SEMANA)**" if ev.is_event_week() else ""
            embed.add_field(
                name=f"{ev.name}{semana_label}",
                value=(
                    f"📆 {ev.formatted_datetime()} · ⏳ {ev.days_until()} dias\n"
                    f"📣 <#{ev.channel_id}> · 🆔 `{ev.id}`\n"
                    f"{ev.description}"
                ),
                inline=False,
            )
        embed.set_footer(text=f"{len(self.events)} evento(s) no total.")
        await interaction.response.send_message(embed=embed)

    @evento_group.command(name="remover", description="Remove um evento pelo ID.")
    @app_commands.describe(evento_id="ID do evento (obtido em /evento listar)")
    async def evento_remover(self, interaction: discord.Interaction, evento_id: str):
        event = self.events.get(evento_id)
        if event is None:
            await interaction.response.send_message(
                f"❌ Evento com ID `{evento_id}` não encontrado.", ephemeral=True,
            )
            return
        await self._delete_event_db(evento_id)
        del self.events[evento_id]
        await interaction.response.send_message(
            f"🗑️ Evento **{event.name}** (`{evento_id}`) removido com sucesso."
        )

    @evento_group.command(name="testar", description="Força o envio imediato de lembretes (para testes).")
    async def evento_testar(self, interaction: discord.Interaction):
        if not self.events:
            await interaction.response.send_message("Nenhum evento para testar.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        for event in self.events.values():
            await self._send_reminder(event)
        await interaction.followup.send(
            f"✅ {len(self.events)} lembrete(s) enviado(s).", ephemeral=True
        )

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


# ── setup ─────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    await bot.add_cog(EventsCog(bot))
