# Marketplace Discord Bot

A Python Discord bot that tracks user-defined marketplace searches and sends
notifications when it discovers new matching listings.

The application is designed around interchangeable listing providers. A
reliable mock provider will support development and demos, while Facebook
Marketplace support will remain an experimental Playwright integration.

## Current status

The Discord bot stores user-owned watches in a local SQLite database. Its
central scanner searches through interchangeable providers, applies query and
price filters, deduplicates matches, and sends direct-message notifications.
Manual and scheduled scans use the same workflow. The reliable mock provider
is the default; an anonymous-first Facebook Marketplace provider is available
as an explicitly experimental option.

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
py -3 -m venv .venv
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

## Run the bot

Add your bot token and test-server ID to the local `.env` file, then run:

```bash
python main.py
```

The development server receives these slash commands:

- `/watch add`
- `/watch list`
- `/watch remove`
- `/scan`
- `/status`

`/watch add`, `/watch list`, and `/watch remove` persist watches between bot
restarts. By default, local data is stored in `data/marketplace.db`; set
`DATABASE_PATH` in `.env` to use another location. Database files are ignored
by Git. `/scan` runs all enabled watches immediately; the same scan runs in the
background every `SCAN_INTERVAL_MINUTES` (30 minutes by default).

Set `FACEBOOK_MARKETPLACE_LOCATION` to the location slug used in Marketplace
URLs, such as `detroit` or `ann-arbor`. It defaults to `detroit`. When creating
a watch, `/watch add` offers `mock` and experimental `facebook` provider
choices; existing behavior remains on `mock` unless Facebook is selected.

## Listing providers

Every marketplace provider implements the asynchronous `ListingProvider`
contract and returns the same `Listing` model. This keeps marketplace-specific
behavior outside the scanner and Discord UI. `MockProvider` loads tracked data
from `data/sample_listings.json`, making development and demonstrations
repeatable without external network access.

`FacebookProvider` uses a temporary headless Chromium browser to load one
bounded, location-scoped search page. It extracts stable
`/marketplace/item/<id>` links and normalizes their title, price, URL, and
optional image without relying on generated CSS classes. It stores no Facebook
credentials or persistent browser session.

Test anonymous access independently from Discord:

```bash
python -m scripts.check_facebook_access --query "office chair"
```

Facebook may redirect anonymous browsers to login, present a challenge, time
out, or change its markup. Those cases produce a clear provider error; the
scanner records a failure for that watch and continues scanning other watches.
The implementation does not attempt CAPTCHA solving, proxy rotation,
fingerprint spoofing, or checkpoint circumvention.

When a matching listing has not been seen for that watch, the bot saves its
stable external ID and sends the watch owner a Discord direct message. Saving
first prevents duplicate alerts on later manual or scheduled scans. A failure
in one watch or provider is logged without stopping the remaining watches.

## Verify the setup

```bash
python main.py
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

CI parses a saved, sanitized Marketplace HTML fixture and never depends on
live Facebook access. The application remains runnable and testable with mock
data if Facebook changes or blocks automated access.
