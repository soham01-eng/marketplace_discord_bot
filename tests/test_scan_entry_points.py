"""Tests that manual and scheduled scans share the same core workflow."""

from unittest.mock import AsyncMock

from src.bot import _format_last_scan, create_bot
from src.database import Database
from src.scanner import ScanResult


class FakeResponse:
    """Capture a deferred Discord interaction response."""

    def __init__(self) -> None:
        self.deferred = False

    async def defer(self, *, ephemeral: bool, thinking: bool) -> None:
        self.deferred = ephemeral and thinking


class FakeFollowup:
    """Capture the follow-up sent after a deferred response."""

    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send(self, message: str, *, ephemeral: bool) -> None:
        self.messages.append((message, ephemeral))


class FakeInteraction:
    """Provide the interaction attributes used by the scan command."""

    def __init__(self) -> None:
        self.response = FakeResponse()
        self.followup = FakeFollowup()


async def test_manual_and_scheduled_scans_use_same_scanner(tmp_path) -> None:
    database = Database(tmp_path / "commands.db")
    bot = create_bot(
        guild_id=123456789,
        database=database,
        scan_interval_minutes=15,
    )
    result = ScanResult(
        watches_scanned=2,
        listings_found=3,
        new_listings=1,
        notifications_sent=1,
        failures=0,
    )
    scan_mock = AsyncMock(return_value=result)
    bot.scanner.scan_watches = scan_mock

    scan_command = bot.tree.get_command("scan", guild=bot.development_guild)
    assert scan_command is not None
    interaction = FakeInteraction()
    await scan_command.callback(interaction)
    await bot.scheduled_scan.coro(bot)

    assert interaction.response.deferred is True
    assert "New matches: 1" in interaction.followup.messages[0][0]
    assert scan_mock.await_count == 2
    assert bot.scheduled_scan.minutes == 15
    database.close()


def test_last_scan_uses_discord_local_timestamp_format() -> None:
    timestamp = "2026-08-21T03:07:45.948065+00:00"

    assert _format_last_scan(None) == "never"
    assert _format_last_scan(timestamp) == ("<t:1787281665:F> (<t:1787281665:R>)")
