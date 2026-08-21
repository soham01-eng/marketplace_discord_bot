# Marketplace Discord Bot

A Python Discord bot that tracks user-defined marketplace searches and sends
notifications when it discovers new matching listings.

The application is designed around interchangeable listing providers. A
reliable mock provider will support development and demos, while Facebook
Marketplace support will remain an experimental Playwright integration.

## Current status

Step 1 is complete: the Python project, local environment template, linting,
and test tooling are initialized. Discord commands and application behavior
will be added in later development steps.

## Technology

- Python 3.11+
- `discord.py`
- SQLite
- Playwright with Chromium
- pytest
- Ruff

## Local setup

### Windows PowerShell

```powershell
git clone https://github.com/soham01-eng/marketplace_discord_bot.git
cd marketplace_discord_bot
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m playwright install chromium
Copy-Item .env.example .env
```

### macOS or Linux

```bash
git clone https://github.com/soham01-eng/marketplace_discord_bot.git
cd marketplace_discord_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m playwright install chromium
cp .env.example .env
```

Do not commit `.env`. It will contain the Discord token once the bot is
created.

## Verify the setup

```bash
python main.py
python -m ruff check .
python -m pytest
```

Facebook Marketplace is an experimental provider. The finished application
will remain runnable and testable with mock data if Facebook changes or blocks
automated access.
