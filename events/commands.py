from __future__ import annotations

import uuid
import re
import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from .model import Event, TIMEZONE, DAILY_FIXED
from . import database as db

DATE_PATTERN = re.compile(r"^\d{2}/\d{2}/\d{4}$")
TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def _lembrete_desc(event: Event) -> str:
    fixos = event.daily_reminders_today() if event.is_today() else list(DAILY_FIXED)
    fixos_str = ", ".join(t.strftime("%H:%M") for t in fixos) if fixos else "nenhum"
    dois_antes = event.two_hours_before().strftime("%H:%M")
    return (
        f"• **Semanal** — toda semana no mesmo dia às 09:00\n"
        f"• **Diário** — na semana do evento: {fixos_str}\n"
        f"• **2h antes** — no dia do evento às {dois_antes}"
    )


def register(cog) -> app_commands.Group:
    """Cria e retorna o grupo /evento com todos os subcomandos."""

    grupo = app_commands.Group(
        name="evento",
        description="Gerenciamento de eventos com lembretes automáticos.",
    )

    # ── /evento adicionar ─────────────────────────────────────────────────────
    @grupo.command(
        name="adicionar", description="Registra um novo evento para ser lembrado."
    )
    @app_commands.describe(
        nome="Nome do evento",
        data="Data no formato DD/MM/AAAA (ex: 30/03/2026)",
        horario="Horário no formato HH:MM (ex: 14:30)",
        descricao="Descrição do evento",
        canal="Canal onde os lembretes serão enviados",
    )
    async def adicionar(
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
                "❌ Horário inválido. Ex: `14:30`",
                ephemeral=True,
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
        await db.save_event(event)
        cog.events[event_id] = event

        embed = discord.Embed(
            title="✅ Evento registrado!", color=discord.Color.green()
        )
        embed.add_field(name="📌 Nome", value=nome, inline=False)
        embed.add_field(name="🗓 Data", value=event.formatted_datetime(), inline=True)
        embed.add_field(
            name="⏳ Faltam", value=f"{event.days_until()} dias", inline=True
        )
        embed.add_field(name="📣 Canal", value=canal.mention, inline=True)
        embed.add_field(name="🔔 Lembretes", value=_lembrete_desc(event), inline=False)
        embed.set_footer(text=f"ID: {event_id} • Use /evento listar para ver todos.")
        await interaction.response.send_message(embed=embed)

    # ── /evento listar ────────────────────────────────────────────────────────
    @grupo.command(name="listar", description="Lista todos os eventos registrados.")
    async def listar(interaction: discord.Interaction):
        cog._purge_past_events()
        if not cog.events:
            await interaction.response.send_message(
                "📭 Nenhum evento registrado. Use `/evento adicionar` para criar um.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🗓 Eventos Registrados", color=discord.Color.blurple()
        )
        for ev in sorted(cog.events.values(), key=lambda e: (e.date, e.time)):
            semana_label = " 🚨 **(ESTA SEMANA)**" if ev.is_event_week() else ""
            embed.add_field(name="", value="\u200b", inline=False)
            embed.add_field(
                name=f"{ev.name} {semana_label}",
                value=(
                    f"* {ev.description}\n"
                    f"🗓 {ev.formatted_datetime()} ({ev.days_until()} dias)\n"
                    f"📣 <#{ev.channel_id}> · 🆔 `{ev.id}`"
                ),
                inline=False,
            )
        embed.set_footer(text=f"{len(cog.events)} evento(s) no total.")
        await interaction.response.send_message(embed=embed)

    # ── /evento remover ───────────────────────────────────────────────────────
    @grupo.command(name="remover", description="Remove um evento pelo ID.")
    @app_commands.describe(evento_id="ID do evento (obtido em /evento listar)")
    async def remover(interaction: discord.Interaction, evento_id: str):
        event = cog.events.get(evento_id)
        if event is None:
            await interaction.response.send_message(
                f"❌ Evento com ID `{evento_id}` não encontrado.",
                ephemeral=True,
            )
            return
        await db.delete_event(evento_id)
        del cog.events[evento_id]
        await interaction.response.send_message(
            f"🗑️ Evento **{event.name}** (`{evento_id}`) removido com sucesso."
        )

    # ── /evento editar ────────────────────────────────────────────────────────
    @grupo.command(
        name="editar", description="Edita um evento existente que ainda vai acontecer."
    )
    @app_commands.describe(
        evento_id="ID do evento (obtido em /evento listar)",
        nome="Novo nome do evento (opcional)",
        data="Nova data no formato DD/MM/AAAA (opcional)",
        horario="Novo horário no formato HH:MM (opcional)",
        descricao="Nova descrição do evento (opcional)",
        canal="Novo canal para os lembretes (opcional)",
    )
    async def editar(
        interaction: discord.Interaction,
        evento_id: str,
        nome: Optional[str] = None,
        data: Optional[str] = None,
        horario: Optional[str] = None,
        descricao: Optional[str] = None,
        canal: Optional[discord.TextChannel] = None,
    ):
        event = cog.events.get(evento_id)
        if event is None:
            await interaction.response.send_message(
                f"❌ Evento com ID `{evento_id}` não encontrado ou já aconteceu.",
                ephemeral=True,
            )
            return
        if event.is_past():
            await interaction.response.send_message(
                f"❌ Evento **{event.name}** já aconteceu. Não é possível editá-lo.",
                ephemeral=True,
            )
            return

        nova_data = event.date
        novo_horario = event.time
        novo_nome = nome if nome is not None else event.name
        nova_descricao = descricao if descricao is not None else event.description
        novo_canal_id = canal.id if canal is not None else event.channel_id

        if data is not None:
            if not DATE_PATTERN.match(data.strip()):
                await interaction.response.send_message(
                    "❌ Formato de data inválido. Use **DD/MM/AAAA** — ex: `30/03/2026`",
                    ephemeral=True,
                )
                return
            try:
                nova_data = datetime.datetime.strptime(data.strip(), "%d/%m/%Y").date()
            except ValueError:
                await interaction.response.send_message(
                    "❌ Data inválida. Ex: `30/03/2026`",
                    ephemeral=True,
                )
                return

        if horario is not None:
            if not TIME_PATTERN.match(horario.strip()):
                await interaction.response.send_message(
                    "❌ Formato de horário inválido. Use **HH:MM** — ex: `14:30`",
                    ephemeral=True,
                )
                return
            try:
                novo_horario = datetime.datetime.strptime(
                    horario.strip(), "%H:%M"
                ).time()
            except ValueError:
                await interaction.response.send_message(
                    "❌ Horário inválido. Ex: `14:30`",
                    ephemeral=True,
                )
                return

        novo_dt = datetime.datetime.combine(nova_data, novo_horario, tzinfo=TIMEZONE)
        if novo_dt <= datetime.datetime.now(tz=TIMEZONE):
            await interaction.response.send_message(
                "❌ O evento com os novos dados já teria passado! Informe data e horário futuros.",
                ephemeral=True,
            )
            return

        event_atualizado = Event(
            id=event.id,
            name=novo_nome,
            date=nova_data,
            time=novo_horario,
            description=nova_descricao,
            channel_id=novo_canal_id,
            created_by=event.created_by,
        )
        await db.update_event(event_atualizado)
        cog.events[evento_id] = event_atualizado

        alteracoes = []
        if nome is not None:
            alteracoes.append(f"📌 Nome: **{event.name}** → **{novo_nome}**")
        if data is not None or horario is not None:
            alteracoes.append(
                f"🗓 Data/Hora: **{event.formatted_datetime()}** → **{event_atualizado.formatted_datetime()}**"
            )
        if descricao is not None:
            alteracoes.append("📝 Descrição alterada")
        if canal is not None:
            alteracoes.append(f"📣 Canal: <#{event.channel_id}> → {canal.mention}")

        embed = discord.Embed(title="✏️ Evento atualizado!", color=discord.Color.gold())
        embed.add_field(name="🆔 ID", value=evento_id, inline=False)
        embed.add_field(name="📌 Nome", value=novo_nome, inline=False)
        embed.add_field(
            name="🗓 Data", value=event_atualizado.formatted_datetime(), inline=True
        )
        embed.add_field(
            name="⏳ Faltam", value=f"{event_atualizado.days_until()} dias", inline=True
        )
        embed.add_field(
            name="📣 Canal",
            value=canal.mention if canal else f"<#{event.channel_id}>",
            inline=True,
        )
        embed.add_field(
            name="🔔 Lembretes (atualizados)",
            value=_lembrete_desc(event_atualizado),
            inline=False,
        )
        if alteracoes:
            embed.add_field(
                name="✅ Alterações", value="\n".join(alteracoes), inline=False
            )
        embed.set_footer(text="Use /evento listar para ver todos os eventos.")
        await interaction.response.send_message(embed=embed)

    # ── /evento testar ────────────────────────────────────────────────────────
    @grupo.command(
        name="testar", description="Força o envio imediato de lembretes (para testes)."
    )
    async def testar(interaction: discord.Interaction):
        if not cog.events:
            await interaction.response.send_message(
                "Nenhum evento para testar.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        for event in cog.events.values():
            await cog._send_reminder(event)
        await interaction.followup.send(
            f"✅ {len(cog.events)} lembrete(s) enviado(s).", ephemeral=True
        )

    return grupo
