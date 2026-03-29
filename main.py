import discord
from discord.ext import commands
import asyncio
import os

# ── Intents ──────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # necessário para prefix commands (opcional)


# ── Bot ───────────────────────────────────────────────────────────────────────
class EventBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )

    async def setup_hook(self):
        """Carrega cogs e sincroniza slash commands."""
        await self.load_extension("events_cog")
        # Sync global (pode demorar até 1h para aparecer no Discord).
        # Para testes rápidos, use sync(guild=discord.Object(id=SEU_GUILD_ID)).
        await self.tree.sync()
        print("✅ Slash commands sincronizados.")

    async def on_ready(self):
        print(f"🤖 Bot online como {self.user} (ID: {self.user.id})")
        print("─" * 40)


bot = EventBot()


@bot.command()
async def ping(ctx: commands.Context):
    await ctx.send("pong!")


if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_TOKEN")  # export DISCORD_TOKEN="seu_token"
    if not TOKEN:
        raise ValueError("Variável de ambiente DISCORD_TOKEN não definida!")
    asyncio.run(bot.start(TOKEN))
