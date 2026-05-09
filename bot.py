import os
import json
import logging
import asyncio
import httpx
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
from telegram.constants import ParseMode

# ─── Configuration ────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID        = os.environ["TELEGRAM_CHAT_ID"]
# Send every Tuesday at 18:00 (Epic usually drops games around 17:00 UTC)
NOTIFY_DAY     = "tue"
NOTIFY_HOUR    = 18
NOTIFY_MINUTE  = 0
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

EPIC_API = (
    "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
    "?locale=en-US&country=US&allowCountries=US"
)


def fetch_free_games() -> list[dict]:
    """Return a list of currently free games from the Epic Games Store API."""
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
        upcoming = promotions.get("upcomingPromotionalOffers", [])

        # Active free offer
        for promo_group in offers:
            for offer in promo_group.get("promotionalOffers", []):
                discount = offer.get("discountSetting", {})
                if discount.get("discountPercentage") == 0:
                    free.append(_extract(game, offer, upcoming=False))
                    break

    return free


def _extract(game: dict, offer: dict, upcoming: bool) -> dict:
    title = game.get("title", "Unknown")
    description = game.get("description", "")
    url_slug = None

    # Try to build a store URL
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

    # Thumbnail
    thumbnail = ""
    for img in game.get("keyImages", []):
        if img.get("type") in ("Thumbnail", "DieselGameBox", "OfferImageWide"):
            thumbnail = img.get("url", "")
            break

    end_date = offer.get("endDate", "")

    return {
        "title": title,
        "description": description[:200].rstrip() + ("…" if len(description) > 200 else ""),
        "url": store_url,
        "thumbnail": thumbnail,
        "end_date": end_date,
        "upcoming": upcoming,
    }


def format_message(games: list[dict]) -> str:
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


async def send_notification():
    log.info("Fetching free games…")
    try:
        games = fetch_free_games()
        log.info("Found %d free game(s): %s", len(games), [g["title"] for g in games])
    except Exception as e:
        log.error("Failed to fetch games: %s", e)
        games = []

    message = format_message(games)
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(
        chat_id=CHAT_ID,
        text=message,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )
    log.info("Notification sent to chat %s", CHAT_ID)


async def main():
    log.info("Starting Epic Games Telegram Bot…")

    # Send once immediately on startup so you can verify it works
    await send_notification()

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        send_notification,
        trigger="cron",
        day_of_week=NOTIFY_DAY,
        hour=NOTIFY_HOUR,
        minute=NOTIFY_MINUTE,
        timezone="UTC",
    )
    scheduler.start()
    log.info(
        "Scheduler running — will notify every %s at %02d:%02d UTC",
        NOTIFY_DAY.upper(), NOTIFY_HOUR, NOTIFY_MINUTE,
    )

    # Keep the event loop alive
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
