"""Notification contract and Discord thread implementation."""

import logging
from contextlib import suppress
from dataclasses import replace
from typing import Protocol

import discord

from src.database import Database
from src.models import Listing, Watch

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    """Send newly discovered listings to watch owners."""

    async def notify(
        self,
        discord_user_id: int,
        watch: Watch,
        listing: Listing,
    ) -> None:
        """Notify one user about one normalized listing."""
        ...


class DiscordNotifier:
    """Organize each watch and its listing notifications in one Discord thread."""

    def __init__(
        self,
        client: discord.Client,
        database: Database,
        marketplace_channel_id: int,
    ) -> None:
        self.client = client
        self.database = database
        self.marketplace_channel_id = marketplace_channel_id

    async def ensure_watch_thread(self, watch: Watch):
        """Return the watch thread, creating or replacing it when necessary."""
        if watch.discord_thread_id is not None:
            try:
                return await self._channel(watch.discord_thread_id)
            except (discord.NotFound, LookupError):
                logger.warning(
                    "Discord thread %s for watch %s no longer exists; recreating it",
                    watch.discord_thread_id,
                    watch.id,
                )

        parent = await self._channel(self.marketplace_channel_id)
        create_thread = getattr(parent, "create_thread", None)
        if create_thread is None:
            raise RuntimeError(
                "DISCORD_MARKETPLACE_CHANNEL_ID must reference a text channel"
            )

        thread = await create_thread(
            name=_thread_name(watch),
            type=discord.ChannelType.public_thread,
            auto_archive_duration=1440,
            reason=f"Marketplace watch #{watch.id}",
        )
        try:
            stored_watch = replace(watch, discord_thread_id=thread.id)
            await thread.send(
                content=f"<@{watch.discord_user_id}> created a marketplace watch.",
                embed=_watch_summary_embed(stored_watch),
            )
            if not self.database.update_watch_thread_id(watch.id, thread.id):
                raise RuntimeError(
                    f"Watch #{watch.id} disappeared before its thread was saved"
                )
        except Exception:
            with suppress(Exception):
                await thread.edit(
                    archived=True,
                    reason=f"Marketplace watch #{watch.id} setup failed",
                )
            raise
        return thread

    async def archive_watch_thread(self, watch: Watch) -> None:
        """Archive a watch thread when its watch is removed."""
        if watch.discord_thread_id is None:
            return
        try:
            thread = await self._channel(watch.discord_thread_id)
        except (discord.NotFound, LookupError):
            logger.info(
                "Watch %s was removed after its Discord thread had already disappeared",
                watch.id,
            )
            return
        await thread.send(content=f"Watch #{watch.id} was removed.")
        await thread.edit(
            archived=True,
            reason=f"Marketplace watch #{watch.id} removed",
        )

    async def notify(
        self,
        discord_user_id: int,
        watch: Watch,
        listing: Listing,
    ) -> None:
        """Send a listing embed to the public thread assigned to the watch."""
        thread = await self.ensure_watch_thread(watch)
        price = (
            f"${listing.price:,.2f}"
            if listing.price is not None
            else "Price unavailable"
        )
        embed = discord.Embed(
            title=listing.title,
            url=listing.url,
            description=price,
            color=discord.Color.green(),
        )
        embed.add_field(name="Source", value=listing.source.title())
        embed.add_field(name="Watch", value=f'#{watch.id}: "{watch.query}"')
        if listing.image_url is not None:
            embed.set_thumbnail(url=listing.image_url)

        await thread.send(
            content=f"<@{discord_user_id}> New marketplace listing found!",
            embed=embed,
        )

    async def _channel(self, channel_id: int):
        """Resolve a cached Discord channel or fetch it from the API."""
        channel = self.client.get_channel(channel_id)
        if channel is None:
            channel = await self.client.fetch_channel(channel_id)
        if channel is None:
            raise LookupError(f"Discord channel {channel_id} was not found")
        return channel


def _thread_name(watch: Watch) -> str:
    """Build a readable Discord thread name within the 100-character limit."""
    normalized_query = " ".join(watch.query.split())
    return f"Watch #{watch.id} — {normalized_query}"[:100]


def _watch_summary_embed(watch: Watch) -> discord.Embed:
    """Create the first message that documents a watch's active settings."""
    max_price = (
        f"${watch.max_price:,.2f}" if watch.max_price is not None else "No maximum"
    )
    embed = discord.Embed(
        title=f"Watch #{watch.id}: {watch.query}",
        description="New matching listings will be posted in this thread.",
        color=discord.Color.blue(),
    )
    embed.add_field(name="Provider", value=watch.provider.title())
    embed.add_field(name="Maximum price", value=max_price)
    embed.add_field(name="Status", value="Active")
    return embed
