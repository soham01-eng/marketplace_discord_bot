"""Notification contract and Discord implementation."""

from typing import Protocol

import discord

from src.models import Listing, Watch


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
    """Send new-listing notifications as direct-message embeds."""

    def __init__(self, client: discord.Client) -> None:
        self.client = client

    async def notify(
        self,
        discord_user_id: int,
        watch: Watch,
        listing: Listing,
    ) -> None:
        """Send a basic listing embed to the Discord user who owns a watch."""
        user = self.client.get_user(discord_user_id)
        if user is None:
            user = await self.client.fetch_user(discord_user_id)

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

        await user.send(content="New marketplace listing found!", embed=embed)
