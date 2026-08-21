"""Application entry point for the Marketplace Discord Bot."""

import logging

from dotenv import load_dotenv

from src.bot import run_bot
from src.config import ConfigurationError, load_settings


def main() -> None:
    """Load local configuration and start the Discord bot."""
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = load_settings()
    except ConfigurationError as error:
        raise SystemExit(f"Configuration error: {error}") from error

    run_bot(
        settings.discord_token,
        settings.discord_guild_id,
        settings.database_path,
    )


if __name__ == "__main__":
    main()
