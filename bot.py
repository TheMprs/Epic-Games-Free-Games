import os
import json
import logging
import httpx
from datetime import datetime, time as dtime, timezone
from pathlib import Path
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

# ─── Configuration ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
SUBSCRIBERS_FILE = Path("subscribers.json")
NOTIFY_DAY      = "thu"
NOTIFY_HOUR     = 15
NOTIFY_MINUTE   = 57
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

EPIC_API = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=en-US&country=US&allowCountries=US"
)


# ─── Subscriber storage ───────────────────────────────────────────────────────

def load_subscribers() -> set:
    if SUBSCRIBERS_FILE.exists():
        return set(json.loads(SUBSCRIBERS_FILE.read_text()))
    return set()

def save_subscribers(subs: set):
    SUBSCRIBERS_FILE.write_text(json.dumps(list(subs)))


# ─── Epic Games API ───────────────────────────────────────────────────────────

def fetch_free_games() -> list:
    with httpx.Client(timeout=15) as client:
        r = client.get(EPIC_API)
        r.raise_for_status()
        data = r.json()

    elements = (
        data.get("data", {})
            .get("Catalog", {})
            .get("searchStore", {})
            .get("elements", [])
    )

    free = []
    for game in elements:
        promotions = game.get("promotions") or {}
        offers = promotions.get("promotionalOffers", [])

        for promo_group in offers:
            for offer in promo_group.get("promotionalOffers", []):
                if offer.get("discountSetting", {}).get("discountPercentage") == 0:
                    free.append(_extract(game, offer))
                    break

    return free


def _extract(game: dict, offer: dict) -> dict:
    title = game.get("title", "Unknown")
    description = game.get("description", "")

    url_slug = None
    for mapping in game.get("catalogNs", {}).get("mappings", []):
        if mapping.get("pageType") == "productHome":
            url_slug = mapping.get("pageSlug")
            break
    if not url_slug:
        for item in game.get("offerMappings", []):
            if item.get("pageType") == "productHome":
                url_slug = item.get("pageSlug")
                break

    store_url = (
        f"https://store.epicgames.com/en-US/p/{url_slug}"
        if url_slug else "https://store.epicgames.com/en-US/free-games"
    )

    end_date = offer.get("endDate", "")

    return {
        "title": title,
        "description": description[:200].rstrip() + ("…" if len(description) > 200 else ""),
        "url": store_url,
        "end_date": end_date,
    }


def format_message(games: list) -> str:
    if not games:
        return (
            "🎮 <b>Epic Games Free Games</b>\n\n"
            "No free games found this week — check back soon!\n"
            "🔗 <a href='https://store.epicgames.com/en-US/free-games'>Epic Free Games</a>"
        )

    lines = ["🎮 <b>Epic Games — Free This Week!</b>\n"]
    for g in games:
        lines.append(f"🕹 <b>{g['title']}</b>")
        if g["description"]:
            lines.append(f"<i>{g['description']}</i>")
        if g["end_date"]:
            try:
                dt = datetime.fromisoformat(g["end_date"].replace("Z", "+00:00"))
                lines.append(f"⏰ Free until: {dt.strftime('%b %d, %Y')}")
            except ValueError:
                pass
        lines.append(f"🔗 <a href='{g['url']}'>Claim on Epic Store</a>")
        lines.append("")

    lines.append("Enjoy your free games! 🎉")
    return "\n".join(lines)


# ─── Command handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = load_subscribers()

    if chat_id in subs:
        await update.message.reply_text("You're already subscribed! 🎮 I'll notify you every Tuesday.")
        return

    subs.add(chat_id)
    save_subscribers(subs)
    log.info("New subscriber: %s", chat_id)

    await update.message.reply_text(
        "✅ Subscribed! You'll get notified every Tuesday when Epic Games drops new free games.\n\n"
        "Send /end at any time to unsubscribe.\n"
        "Send /games to check the current free games right now!"
    )


async def cmd_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    subs = load_subscribers()

    if chat_id not in subs:
        await update.message.reply_text("You're not subscribed — send /start to subscribe!")
        return

    subs.discard(chat_id)
    save_subscribers(subs)
    log.info("Unsubscribed: %s", chat_id)

    await update.message.reply_text("👋 Unsubscribed. You won't receive notifications anymore.\nSend /start to re-subscribe anytime.")


async def cmd_games(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check current free games on demand."""
    await update.message.reply_text("Fetching current free games… 🔍")
    try:
        games = fetch_free_games()
    except Exception as e:
        await update.message.reply_text(f"Failed to fetch games: {e}")
        return
    await update.message.reply_text(format_message(games), parse_mode=ParseMode.HTML)



# ─── Weekly notification ──────────────────────────────────────────────────────

async def send_weekly_notification(context: ContextTypes.DEFAULT_TYPE):
    subs = load_subscribers()
    if not subs:
        log.info("No subscribers, skipping notification.")
        return

    log.info("Sending weekly notification to %d subscriber(s)…", len(subs))
    try:
        games = fetch_free_games()
    except Exception as e:
        log.error("Failed to fetch games: %s", e)
        return

    message = format_message(games)
    for chat_id in list(subs):
        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)
            log.info("Notified %s", chat_id)
        except Exception as e:
            log.warning("Failed to notify %s: %s — removing from subscribers", chat_id, e)
            subs.discard(chat_id)

    save_subscribers(subs)


# ─── Main ─────────────────────────────────────────────────────────────────────

async def log_schedule(context: ContextTypes.DEFAULT_TYPE):
    for job in context.job_queue.jobs():
        if job.callback == send_weekly_notification:
            log.info("Next scheduled notification: %s", job.next_run_time)
            break


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("end", cmd_end))
    app.add_handler(CommandHandler("games", cmd_games))

    app.job_queue.run_daily(
        send_weekly_notification,
        time=dtime(hour=NOTIFY_HOUR, minute=NOTIFY_MINUTE, tzinfo=timezone.utc),
        days=(4,),  # 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
        name="send_weekly_notification",
    )
    app.job_queue.run_once(log_schedule, when=2)
    log.info(
        "Bot started — polling for commands. Weekly notification: every %s at %02d:%02d UTC",
        NOTIFY_DAY.upper(), NOTIFY_HOUR, NOTIFY_MINUTE
    )

    app.run_polling()


if __name__ == "__main__":
    main()