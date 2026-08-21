"""Discord bot and slash-command definitions."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class MarketplaceBot(commands.Bot):
    """Discord bot configured for rapid command syncing in one development server."""

    def __init__(self, guild_id: int) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.development_guild = discord.Object(id=guild_id)

    async def setup_hook(self) -> None:
        """Synchronize commands to the test server before the bot becomes ready."""
        synced = await self.tree.sync(guild=self.development_guild)
        logger.info(
            "Synchronized %s commands to development server %s",
            len(synced),
            self.development_guild.id,
        )

    async def on_ready(self) -> None:
        """Log a safe startup message once Discord finishes connecting."""
        if self.user is not None:
            logger.info("Bot connected as %s", self.user)


def create_bot(guild_id: int) -> MarketplaceBot:
    """Create a bot instance and register the MVP command placeholders."""
    bot = MarketplaceBot(guild_id)
    watch_group = app_commands.Group(
        name="watch",
        description="Manage marketplace watches",
    )

    @watch_group.command(name="add", description="Create a marketplace watch")
    @app_commands.describe(
        query="What to search for",
        max_price="Optional maximum listing price",
    )
    async def add_watch(
        interaction: discord.Interaction,
        query: str,
        max_price: float | None = None,
    ) -> None:
        normalized_query = query.strip()
        if not normalized_query:
            await interaction.response.send_message(
                "Query cannot be empty.",
                ephemeral=True,
            )
            return
        if max_price is not None and max_price < 0:
            await interaction.response.send_message(
                "Maximum price cannot be negative.",
                ephemeral=True,
            )
            return

        price_text = (
            f" with a maximum price of ${max_price:,.2f}"
            if max_price is not None
            else " with no maximum price"
        )
        await interaction.response.send_message(
            f'Watch preview created for "{normalized_query}"{price_text}. '
            "Persistent storage will be added next.",
            ephemeral=True,
        )

    @watch_group.command(name="list", description="List your marketplace watches")
    async def list_watches(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Watch listing is connected. Persistent watches will be added next.",
            ephemeral=True,
        )

    @watch_group.command(name="remove", description="Remove a marketplace watch")
    @app_commands.describe(watch_id="Numeric ID of the watch to remove")
    async def remove_watch(
        interaction: discord.Interaction,
        watch_id: int,
    ) -> None:
        if watch_id <= 0:
            await interaction.response.send_message(
                "Watch ID must be greater than zero.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            f"Watch removal is connected for watch #{watch_id}. "
            "Persistent storage will be added next.",
            ephemeral=True,
        )

    bot.tree.add_command(watch_group, guild=bot.development_guild)

    @bot.tree.command(
        name="scan",
        description="Run a marketplace scan now",
        guild=bot.development_guild,
    )
    async def scan(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "Manual scanning is connected. Provider scanning will be added later.",
            ephemeral=True,
        )

    @bot.tree.command(
        name="status",
        description="Show bot and scanner status",
        guild=bot.development_guild,
    )
    async def status(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000)
        await interaction.response.send_message(
            "Bot: online\n"
            f"Discord latency: {latency_ms} ms\n"
            "Database: not implemented\n"
            "Scanner: not implemented",
            ephemeral=True,
        )

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        logger.error(
            "Application command failed: %s",
            error,
            exc_info=(type(error), error, error.__traceback__),
        )
        message = "The command could not be completed. Please try again."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    return bot


def run_bot(token: str, guild_id: int) -> None:
    """Connect the configured bot to Discord."""
    bot = create_bot(guild_id)
    bot.run(token, log_handler=None)
