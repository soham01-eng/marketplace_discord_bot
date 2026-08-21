"""Discord bot and slash-command definitions."""

import asyncio
import logging
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.database import Database
from src.notifier import DiscordNotifier
from src.providers import MockProvider
from src.scanner import Scanner, ScanResult

logger = logging.getLogger(__name__)


class MarketplaceBot(commands.Bot):
    """Discord bot configured for rapid command syncing in one development server."""

    def __init__(
        self,
        guild_id: int,
        database: Database,
        scan_interval_minutes: int,
        scanner: Scanner | None = None,
    ) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.development_guild = discord.Object(id=guild_id)
        self.database = database
        self.scan_interval_minutes = scan_interval_minutes
        self.scanner = scanner or Scanner(
            database=database,
            providers={"mock": MockProvider()},
            notifier=DiscordNotifier(self),
        )
        self.scheduled_scan.change_interval(minutes=scan_interval_minutes)

    async def setup_hook(self) -> None:
        """Synchronize commands to the test server before the bot becomes ready."""
        synced = await self.tree.sync(guild=self.development_guild)
        logger.info(
            "Synchronized %s commands to development server %s",
            len(synced),
            self.development_guild.id,
        )
        self.scheduled_scan.start()

    async def on_ready(self) -> None:
        """Log a safe startup message once Discord finishes connecting."""
        if self.user is not None:
            logger.info("Bot connected as %s", self.user)

    async def close(self) -> None:
        """Close Discord and the local database connection."""
        scheduled_task = self.scheduled_scan.get_task()
        self.scheduled_scan.cancel()
        if scheduled_task is not None:
            with suppress(asyncio.CancelledError):
                await scheduled_task
        try:
            await super().close()
        finally:
            self.database.close()

    async def run_scan(self) -> ScanResult:
        """Run the same scanner used by manual and scheduled entry points."""
        return await self.scanner.scan_watches()

    @tasks.loop(minutes=30)
    async def scheduled_scan(self) -> None:
        """Run the shared scanner on the configured interval."""
        try:
            await self.run_scan()
        except Exception:
            logger.exception("Scheduled scan could not be completed")

    @scheduled_scan.before_loop
    async def wait_before_scheduled_scan(self) -> None:
        """Wait for Discord to be ready before sending scheduled notifications."""
        await self.wait_until_ready()


def create_bot(
    guild_id: int,
    database: Database,
    scan_interval_minutes: int = 30,
    scanner: Scanner | None = None,
) -> MarketplaceBot:
    """Create a bot instance and register the MVP commands."""
    bot = MarketplaceBot(
        guild_id,
        database,
        scan_interval_minutes,
        scanner,
    )
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

        watch = bot.database.create_watch(
            discord_user_id=interaction.user.id,
            query=normalized_query,
            max_price=max_price,
        )
        price_text = _format_max_price(watch.max_price)
        await interaction.response.send_message(
            f'Saved watch #{watch.id} for "{watch.query}" '
            f"({price_text}, provider: {watch.provider}).",
            ephemeral=True,
        )

    @watch_group.command(name="list", description="List your marketplace watches")
    async def list_watches(interaction: discord.Interaction) -> None:
        watches = bot.database.list_watches(interaction.user.id)
        if not watches:
            await interaction.response.send_message(
                "You do not have any watches yet. Use `/watch add` to create one.",
                ephemeral=True,
            )
            return

        displayed_watches = watches[:20]
        lines = [
            f'#{watch.id} — "{watch.query}" — {_format_max_price(watch.max_price)} '
            f"— {watch.provider}"
            for watch in displayed_watches
        ]
        if len(watches) > len(displayed_watches):
            lines.append(f"…and {len(watches) - len(displayed_watches)} more.")
        await interaction.response.send_message(
            "Your watches:\n" + "\n".join(lines),
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
        removed = bot.database.delete_watch(watch_id, interaction.user.id)
        if removed:
            message = f"Removed watch #{watch_id}."
        else:
            message = f"Watch #{watch_id} was not found in your watches."
        await interaction.response.send_message(message, ephemeral=True)

    bot.tree.add_command(watch_group, guild=bot.development_guild)

    @bot.tree.command(
        name="scan",
        description="Run a marketplace scan now",
        guild=bot.development_guild,
    )
    async def scan(interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await bot.run_scan()
        await interaction.followup.send(
            "Scan complete.\n"
            f"Watches scanned: {result.watches_scanned}\n"
            f"Listings returned: {result.listings_found}\n"
            f"New matches: {result.new_listings}\n"
            f"Notifications sent: {result.notifications_sent}\n"
            f"Failures: {result.failures}",
            ephemeral=True,
        )

    @bot.tree.command(
        name="status",
        description="Show bot and scanner status",
        guild=bot.development_guild,
    )
    async def status(interaction: discord.Interaction) -> None:
        latency_ms = round(bot.latency * 1000)
        scanner_state = "running" if bot.scanner.is_running else "idle"
        last_scan = _format_last_scan(bot.scanner.last_finished_at)
        await interaction.response.send_message(
            "Bot: online\n"
            f"Discord latency: {latency_ms} ms\n"
            "Database: connected\n"
            f"Scanner: {scanner_state}\n"
            f"Scan interval: {bot.scan_interval_minutes} minutes\n"
            f"Last completed scan: {last_scan}",
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


def run_bot(
    token: str,
    guild_id: int,
    database_path: str | Path,
    scan_interval_minutes: int = 30,
) -> None:
    """Connect the configured bot to Discord."""
    database = Database(database_path)
    try:
        bot = create_bot(guild_id, database, scan_interval_minutes)
        bot.run(token, log_handler=None)
    finally:
        database.close()


def _format_max_price(max_price: float | None) -> str:
    """Format an optional watch price for Discord responses."""
    if max_price is None:
        return "no maximum price"
    return f"maximum ${max_price:,.2f}"


def _format_last_scan(timestamp: str | None) -> str:
    """Format a scanner timestamp using Discord's viewer-local rendering."""
    if timestamp is None:
        return "never"
    unix_timestamp = int(datetime.fromisoformat(timestamp).timestamp())
    return f"<t:{unix_timestamp}:F> (<t:{unix_timestamp}:R>)"
