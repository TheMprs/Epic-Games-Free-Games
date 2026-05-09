# Epic Games Free Games Bot 🎮

A Telegram bot that notifies subscribers every Tuesday when Epic Games drops new free games.

## Commands

| Command | Description |
|---|---|
| `/start` | Subscribe to weekly notifications |
| `/end` | Unsubscribe |
| `/games` | Check the current free games right now |

## Setup

### 1. Create a Telegram bot
Message **@BotFather** on Telegram → `/newbot` → copy the token.

### 2. Install & run locally
```bash
pip install -r requirements.txt
set TELEGRAM_BOT_TOKEN=your_token_here
py bot.py
```

### 3. Deploy to Railway (free)
1. Push this folder to a GitHub repo
2. Go to [railway.app](https://railway.app) → connect your repo
3. Add `TELEGRAM_BOT_TOKEN` as an environment variable
4. Deploy — it runs 24/7 automatically

## Share with friends
Just send them your bot's Telegram username and tell them to type `/start`.
