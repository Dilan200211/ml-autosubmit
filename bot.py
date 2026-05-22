"""
MonsterLab ClipIt Auto-Submit Telegram Bot

A Telegram bot that automates clip URL submissions to MonsterLab.io's
ClipIt platform with rate limiting, bulk submissions, and earnings tracking.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from aiohttp import web

from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)
from telegram.constants import ParseMode

from config import load_config, Config
from monsterlab_api import MonsterLabAPI
from database import Database
from scheduler import SubmissionScheduler, RateLimiter
from utils import (
    is_valid_url,
    detect_platform,
    extract_urls,
    format_earnings,
    format_time_ago,
    truncate,
    escape_md,
    PLATFORM_EMOJIS as PLATFORM_EMOJI,
)

# ─── Logging Setup ───────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# Quiet down noisy libs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
logger = logging.getLogger("monsterlab_bot")

# ─── Globals ─────────────────────────────────────────────────────────────────

config: Config = None
db: Database = None
api: MonsterLabAPI = None
scheduler: SubmissionScheduler = None
cached_campaigns: list = []  # cached list of active campaigns
default_campaign_id: str = None  # auto-selected or user-set default
campaign_passwords: dict = {}  # campaign_id -> password mapping

# Conversation states for bulk mode
BULK_URLS = 0


async def refresh_campaigns():
    """Fetch campaigns from API and cache them. Auto-set default if needed."""
    global cached_campaigns, default_campaign_id
    try:
        result = await api.get_campaigns()
        if result.get("success"):
            cached_campaigns = result.get("data", [])
            # Auto-set default to first campaign if not already set
            if not default_campaign_id and cached_campaigns:
                default_campaign_id = cached_campaigns[0].get("campaignId")
                logger.info(f"Auto-selected campaign: {default_campaign_id} ({cached_campaigns[0].get('name')})")
            return True
    except Exception as e:
        logger.error(f"Failed to fetch campaigns: {e}")
    return False


def get_campaign_id(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    """Get the active campaign ID — user override > global default."""
    return context.user_data.get("default_campaign") or default_campaign_id


def get_campaign_password(campaign_id: str | None) -> str | None:
    """Get the password for a campaign, if set."""
    if campaign_id:
        return campaign_passwords.get(campaign_id)
    return None


def build_campaign_keyboard() -> InlineKeyboardMarkup | None:
    """Build inline keyboard buttons for all cached campaigns."""
    if not cached_campaigns:
        return None

    buttons = []
    for camp in cached_campaigns[:8]:  # max 8 buttons
        camp_id = camp.get("campaignId", "")
        name = camp.get("name", "Unknown")
        # Show ✅ next to currently selected
        prefix = "✅ " if camp_id == default_campaign_id else ""
        # Truncate name for button
        label = f"{prefix}{name[:30]}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"camp:{camp_id}")])

    return InlineKeyboardMarkup(buttons)


# ─── Auth Decorator ──────────────────────────────────────────────────────────

def authorized(func):
    """Decorator to restrict commands to authorized user only."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != config.authorized_user_id:
            await update.message.reply_text("⛔ Unauthorized. This bot is private.")
            logger.warning(f"Unauthorized access attempt by user {update.effective_user.id}")
            return
        return await func(update, context)
    return wrapper


# ─── Submission Callback ─────────────────────────────────────────────────────

async def on_submission_complete(queue_id: int, url: str, success: bool, result: dict):
    """Called by scheduler when a queued submission completes."""
    # This will be set up with the application's bot instance
    pass


# ─── Bot Command Handlers ────────────────────────────────────────────────────

@authorized
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome = (
        "🧪 *MONSTERLAB ClipIt Auto\\-Submit Bot*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Submit your social media clips to MonsterLab automatically\\!\n\n"
        "📋 *Quick Commands:*\n"
        "• Send any clip URL to auto\\-submit\n"
        "• `/submit <url>` \\- Submit a single clip\n"
        "• `/bulk` \\- Submit multiple URLs at once\n"
        "• `/status` \\- View today's stats\n"
        "• `/earnings` \\- Check your earnings\n"
        "• `/help` \\- Full command list\n\n"
        "💡 _Just paste a URL and I'll handle the rest\\!_"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command."""
    help_text = (
        "🧪 *MONSTERLAB Bot \\- Commands*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📤 *Submission:*\n"
        "`/submit <url>` \\- Submit a single clip URL\n"
        "`/bulk` \\- Start bulk submission mode\n"
        "`/setcampaign <id>` \\- Set default campaign\n"
        "`/setpassword <pw>` \\- Set campaign password\n\n"
        "📊 *Monitoring:*\n"
        "`/status` \\- Today's submission stats\n"
        "`/queue` \\- View pending queue\n"
        "`/history` \\- Recent submissions\n"
        "`/earnings` \\- Check earnings\n"
        "`/campaigns` \\- List active campaigns\n"
        "`/ratelimit` \\- Current rate limit status\n\n"
        "🛠 *Management:*\n"
        "`/cancel` \\- Cancel all pending submissions\n"
        "`/validate` \\- Validate your API key\n\n"
        "💡 *Tip:* Just paste a URL \\(no command needed\\) and "
        "I'll auto\\-detect and submit it\\!"
    )
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_submit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /submit <url> command."""
    if not context.args:
        await update.message.reply_text(
            "❌ Please provide a URL.\n\n"
            "Usage: `/submit https://tiktok.com/...`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    url = context.args[0].strip()
    await _process_single_url(update, url, context)


async def _process_single_url(update: Update, url: str, context: ContextTypes.DEFAULT_TYPE):
    """Process and queue a single URL for submission."""
    # Validate URL
    if not is_valid_url(url):
        await update.message.reply_text(f"❌ Invalid URL: `{escape_md(truncate(url, 60))}`", parse_mode=ParseMode.MARKDOWN_V2)
        return

    # Detect platform
    platform = detect_platform(url)
    emoji = PLATFORM_EMOJI.get(platform, "🔗")

    # Check for duplicates
    if await db.is_duplicate(url):
        await update.message.reply_text(
            f"⚠️ Already submitted: {emoji} `{escape_md(truncate(url, 50))}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        return

    # Get campaign ID (required by MonsterLab API)
    campaign_id = get_campaign_id(context)

    if not campaign_id:
        # Try refreshing campaigns first
        await refresh_campaigns()
        campaign_id = get_campaign_id(context)

    if not campaign_id:
        keyboard = build_campaign_keyboard()
        if keyboard:
            await update.message.reply_text(
                "⚠️ *No campaign selected\!*\n\nTap a campaign below to select it:",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text(
                "⚠️ *No campaigns found\!*\n\n"
                "Run `/campaigns` to refresh the list\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        return

    try:
        # Add to queue
        campaign_pw = get_campaign_password(campaign_id)
        queue_id = await db.add_to_queue(url, campaign_id=campaign_id, password=campaign_pw)
        scheduler.notify_new_item()

        # Get queue position
        pending = await db.get_queue_count()
        rate_stats = scheduler.rate_limiter.get_stats()

        status_msg = (
            f"⏳ *Queued for submission*\n\n"
            f"{emoji} `{escape_md(truncate(url, 55))}`\n"
            f"🎯 Campaign: `{escape_md(campaign_id)}`\n"
            f"📍 Queue position: *{escape_md(str(pending))}*\n"
        )

        if rate_stats["can_submit_now"]:
            status_msg += "🚀 Submitting shortly\\.\\.\\."
        else:
            wait = rate_stats["seconds_until_available"]
            status_msg += f"⏱ Rate limit: ~{escape_md(str(int(wait)))}s wait"

        await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN_V2)

    except Exception as e:
        await update.message.reply_text(f"❌ Error queuing: {str(e)}")


@authorized
async def cmd_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /bulk command — start bulk URL input mode."""
    await update.message.reply_text(
        "📦 *Bulk Submission Mode*\n\n"
        "Send me your URLs \\(one per line\\)\\.\n"
        "I'll queue them all for submission\\.\n\n"
        "Send `/done` when finished, or `/cancel` to abort\\.",
        parse_mode=ParseMode.MARKDOWN_V2,
    )
    context.user_data["bulk_mode"] = True
    context.user_data["bulk_urls"] = []
    return BULK_URLS


@authorized
async def bulk_receive_urls(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive URLs during bulk mode."""
    text = update.message.text.strip()

    if text.lower() == "/done":
        return await bulk_done(update, context)

    if text.lower() == "/cancel":
        context.user_data["bulk_mode"] = False
        context.user_data["bulk_urls"] = []
        await update.message.reply_text("❌ Bulk mode cancelled.")
        return ConversationHandler.END

    # Extract URLs from the message
    urls = extract_urls(text)

    if not urls:
        # Maybe they sent URLs one per line without http
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines:
            if not line.startswith("http"):
                line = "https://" + line
            if is_valid_url(line):
                urls.append(line)

    if urls:
        context.user_data.setdefault("bulk_urls", []).extend(urls)
        count = len(context.user_data["bulk_urls"])
        await update.message.reply_text(
            f"✅ Added {len(urls)} URL(s). Total: {count}\n"
            f"Send more URLs or `/done` to submit all."
        )
    else:
        await update.message.reply_text("⚠️ No valid URLs found. Try again or `/done` to finish.")

    return BULK_URLS


@authorized
async def bulk_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Finish bulk mode and queue all URLs."""
    urls = context.user_data.get("bulk_urls", [])
    context.user_data["bulk_mode"] = False

    if not urls:
        await update.message.reply_text("📦 No URLs to submit. Bulk mode ended.")
        return ConversationHandler.END

    campaign_id = get_campaign_id(context)

    if not campaign_id:
        await refresh_campaigns()
        campaign_id = get_campaign_id(context)

    if not campaign_id:
        await update.message.reply_text(
            "⚠️ *No campaign selected\!*\n\n"
            "Run `/campaigns` then `/setcampaign camp_xxxxx`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        context.user_data["bulk_urls"] = []
        return ConversationHandler.END

    # Add all to queue
    added, duplicates = await db.add_bulk_to_queue(urls, campaign_id=campaign_id)
    scheduler.notify_new_item()

    msg = (
        f"📦 *Bulk Submission Complete*\n\n"
        f"✅ Queued: *{escape_md(str(added))}* clips\n"
    )
    if duplicates > 0:
        msg += f"⚠️ Duplicates skipped: *{escape_md(str(duplicates))}*\n"

    pending = await db.get_queue_count()
    msg += f"\n📍 Total in queue: *{escape_md(str(pending))}*"

    context.user_data["bulk_urls"] = []
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    return ConversationHandler.END


@authorized
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command — show today's stats."""
    stats = await db.get_today_stats()
    queue_status = await scheduler.get_queue_status()
    rate = queue_status["rate_limit"]

    msg = (
        "📊 *Today's Stats*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"✅ Submitted: *{escape_md(str(stats['submitted']))}*\n"
        f"⏳ Pending: *{escape_md(str(stats['pending']))}*\n"
        f"❌ Failed: *{escape_md(str(stats['failed']))}*\n"
        f"📈 Total: *{escape_md(str(stats['total']))}*\n\n"
        "⚡ *Rate Limits:*\n"
        f"  Per min: {escape_md(str(rate['minute_count']))}/{escape_md(str(rate['minute_limit']))}\n"
        f"  Per hour: {escape_md(str(rate['hour_count']))}/{escape_md(str(rate['hour_limit']))}\n"
    )

    if queue_status["eta_seconds"] > 0:
        mins = int(queue_status["eta_seconds"] // 60)
        secs = int(queue_status["eta_seconds"] % 60)
        msg += f"\n⏱ Est\\. completion: ~{escape_md(str(mins))}m {escape_md(str(secs))}s"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_queue(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /queue command — show pending queue."""
    queue_status = await scheduler.get_queue_status()
    pending = queue_status["pending"]

    if pending == 0:
        await update.message.reply_text("📭 Queue is empty. Send a URL to get started!")
        return

    rate = queue_status["rate_limit"]
    msg = (
        f"📬 *Submission Queue*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"⏳ Pending: *{escape_md(str(pending))}* clips\n"
        f"🏃 Scheduler: {'🟢 Running' if queue_status['is_running'] else '🔴 Stopped'}\n"
    )

    if rate["can_submit_now"]:
        msg += "🚀 Status: *Submitting now*\n"
    else:
        wait = rate["seconds_until_available"]
        msg += f"⏱ Next submit in: *{escape_md(str(int(wait)))}s*\n"

    if queue_status["eta_seconds"] > 0:
        mins = int(queue_status["eta_seconds"] // 60)
        secs = int(queue_status["eta_seconds"] % 60)
        msg += f"\n📍 Est\\. completion: ~{escape_md(str(mins))}m {escape_md(str(secs))}s"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command — show recent submissions."""
    limit = 10
    if context.args:
        try:
            limit = min(int(context.args[0]), 25)
        except ValueError:
            pass

    submissions = await db.get_recent_submissions(limit)

    if not submissions:
        await update.message.reply_text("📭 No submissions yet.")
        return

    msg = f"📜 *Last {len(submissions)} Submissions*\n━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    for sub in submissions:
        platform = sub.get("platform", "unknown")
        emoji = PLATFORM_EMOJI.get(platform, "🔗")
        status_emoji = {"success": "✅", "failed": "❌", "pending": "⏳"}.get(sub["status"], "❓")

        url_display = truncate(sub["url"], 40)
        time_str = ""
        if sub.get("submitted_at"):
            try:
                dt = datetime.fromisoformat(sub["submitted_at"])
                time_str = f" \\- {escape_md(format_time_ago(dt))}"
            except (ValueError, TypeError):
                pass

        sub_id = sub.get("submission_id", "")
        id_str = f" `{escape_md(sub_id)}`" if sub_id else ""

        msg += f"{status_emoji} {emoji} `{escape_md(url_display)}`{id_str}{time_str}\n"

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /earnings command — fetch earnings from MonsterLab."""
    await update.message.reply_text("💰 Fetching earnings...")

    try:
        result = await api.get_account_info()

        if result.get("success"):
            data = result.get("data", {})
            # Try to extract earnings fields (structure may vary)
            est_total = data.get("estimatedEarnings", data.get("earnings", {}).get("total", "N/A"))
            pending = data.get("pendingEarnings", data.get("earnings", {}).get("pending", "N/A"))
            available = data.get("availableEarnings", data.get("earnings", {}).get("available", "N/A"))

            msg = (
                "💰 *MonsterLab Earnings*\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"📊 Est\\. Total: *${escape_md(str(est_total))}*\n"
                f"⏳ Pending: *${escape_md(str(pending))}*\n"
                f"✅ Available: *${escape_md(str(available))}*\n"
            )
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        else:
            await update.message.reply_text(
                f"⚠️ Could not fetch earnings: {result.get('error', 'Unknown error')}\n\n"
                "The account info endpoint may differ from what we expected. "
                "Check your MonsterLab dashboard directly."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching earnings: {str(e)}")


@authorized
async def cmd_campaigns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /campaigns command — list active campaigns with selection buttons."""
    await update.message.reply_text("🎯 Fetching campaigns...")

    try:
        await refresh_campaigns()

        if cached_campaigns:
            campaigns = cached_campaigns

            if not campaigns:
                await update.message.reply_text("📭 No active campaigns found.")
                return

            msg = f"🎯 *Active Campaigns* \\({escape_md(str(len(campaigns)))}\\)\n━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

            for camp in campaigns[:10]:
                name = camp.get("name", "Unknown")
                camp_id = camp.get("campaignId", "")
                desc = camp.get("description", "")
                is_active = camp_id == default_campaign_id

                marker = "✅" if is_active else "📌"
                msg += f"{marker} *{escape_md(name)}*"
                if is_active:
                    msg += " \\(selected\\)"
                msg += "\n"

                if desc:
                    msg += f"   {escape_md(truncate(desc, 55))}\n"

                # Payout rates
                rates = camp.get("payoutRates", {})
                if rates:
                    rate_parts = []
                    for platform, rate in rates.items():
                        emoji = PLATFORM_EMOJI.get(platform, "")
                        rate_parts.append(f"{emoji}${escape_md(str(rate))}")
                    separator = " \\| "
                    rates_str = separator.join(rate_parts)
                    msg += f"   💵 {rates_str}\n"

                msg += "\n"

            msg += "👇 *Tap a button below to select a campaign:*"

            keyboard = build_campaign_keyboard()
            await update.message.reply_text(
                msg,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=keyboard,
            )
        else:
            await update.message.reply_text("📭 No campaigns found. Check your API key.")

    except Exception as e:
        await update.message.reply_text(f"❌ Error fetching campaigns: {str(e)}")


async def callback_campaign_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button press for campaign selection."""
    global default_campaign_id

    query = update.callback_query
    await query.answer()  # acknowledge the button press

    # Check authorization
    if query.from_user.id != config.authorized_user_id:
        await query.answer("⛔ Unauthorized.", show_alert=True)
        return

    # Extract campaign ID from callback data (format: "camp:camp_123456")
    camp_id = query.data.split(":", 1)[1] if ":" in query.data else ""

    if not camp_id:
        await query.answer("❌ Invalid campaign.", show_alert=True)
        return

    # Set as default
    default_campaign_id = camp_id
    context.user_data["default_campaign"] = camp_id

    # Find campaign name
    camp_name = camp_id
    for camp in cached_campaigns:
        if camp.get("campaignId") == camp_id:
            camp_name = camp.get("name", camp_id)
            break

    # Update the message to show selection confirmation
    await query.edit_message_text(
        f"✅ *Campaign selected\\!*\n\n"
        f"🎯 *{escape_md(camp_name)}*\n"
        f"ID: `{escape_md(camp_id)}`\n\n"
        f"All submissions will now use this campaign\\.\n"
        f"Just paste a URL to submit\\! 🚀",
        parse_mode=ParseMode.MARKDOWN_V2,
    )

    logger.info(f"Campaign selected via button: {camp_id} ({camp_name})")


@authorized
async def cmd_setcampaign(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setcampaign <id> — set default campaign for submissions."""
    global default_campaign_id

    if not context.args:
        user_camp = context.user_data.get("default_campaign")
        active = get_campaign_id(context)
        msg = f"🎯 Active campaign: `{escape_md(str(active or 'None'))}`\n"
        if user_camp:
            msg += f"   \\(user override\\)\n"
        elif default_campaign_id:
            msg += f"   \\(auto\\-detected\\)\n"
        msg += (
            "\nUsage: `/setcampaign camp_123456`\n"
            "Use `/setcampaign clear` to remove override"
        )
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
        return

    campaign_id = context.args[0].strip()
    if campaign_id.lower() == "clear":
        context.user_data.pop("default_campaign", None)
        await update.message.reply_text(
            f"✅ User override cleared\\. Using global default: `{escape_md(str(default_campaign_id or 'None'))}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    else:
        context.user_data["default_campaign"] = campaign_id
        default_campaign_id = campaign_id  # also update global
        await update.message.reply_text(f"✅ Default campaign set to: `{escape_md(campaign_id)}`", parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_setpassword(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /setpassword — set password for a campaign.

    Usage:
        /setpassword <password>           — set for current campaign
        /setpassword <campaign_id> <pw>   — set for specific campaign
        /setpassword clear                — clear password for current campaign
    """
    global campaign_passwords

    current_camp = get_campaign_id(context)

    if not context.args:
        # Show current status
        if current_camp and current_camp in campaign_passwords:
            await update.message.reply_text(
                f"🔒 Password is *set* for campaign `{escape_md(current_camp)}`\\.\n\n"
                f"Use `/setpassword clear` to remove it\\.\n"
                f"Use `/setpassword YOUR_PASSWORD` to change it\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                f"🔓 No password set for campaign `{escape_md(str(current_camp or 'None'))}`\\.\n\n"
                f"Usage:\n"
                f"  `/setpassword YOUR_PASSWORD` — set for current campaign\n"
                f"  `/setpassword camp_id PASSWORD` — set for specific campaign\n"
                f"  `/setpassword clear` — remove password",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        return

    if len(context.args) == 1:
        arg = context.args[0].strip()
        if arg.lower() == "clear":
            if current_camp and current_camp in campaign_passwords:
                del campaign_passwords[current_camp]
                await update.message.reply_text(
                    f"🔓 Password cleared for campaign `{escape_md(current_camp)}`\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await update.message.reply_text("🔓 No password was set.")
        else:
            # Set password for current campaign
            if not current_camp:
                await update.message.reply_text("⚠️ No campaign selected. Select one first with /campaigns")
                return
            campaign_passwords[current_camp] = arg
            await update.message.reply_text(
                f"🔒 Password set for campaign `{escape_md(current_camp)}`\\.\n"
                f"All submissions to this campaign will include the password\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    elif len(context.args) >= 2:
        camp_id = context.args[0].strip()
        pw = " ".join(context.args[1:]).strip()
        campaign_passwords[camp_id] = pw
        await update.message.reply_text(
            f"🔒 Password set for campaign `{escape_md(camp_id)}`\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    logger.info(f"Campaign passwords updated: {len(campaign_passwords)} campaign(s) have passwords")


@authorized
async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cancel command — cancel all pending submissions."""
    cancelled = await db.cancel_all_pending()

    if cancelled == 0:
        await update.message.reply_text("📭 No pending submissions to cancel.")
    else:
        await update.message.reply_text(f"🗑 Cancelled *{escape_md(str(cancelled))}* pending submissions\\.", parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def cmd_validate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /validate command — validate API key."""
    await update.message.reply_text("🔑 Validating API key...")

    try:
        result = await api.validate_key()
        if result.valid:
            await update.message.reply_text("✅ API key is valid!")
        else:
            await update.message.reply_text("❌ API key is INVALID. Please check your .env configuration.")
    except Exception as e:
        await update.message.reply_text(f"❌ Validation error: {str(e)}")


@authorized
async def cmd_ratelimit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ratelimit command — show current rate limit status."""
    stats = scheduler.rate_limiter.get_stats()
    rl_info = api.last_rate_limit_info

    msg = (
        "⚡ *Rate Limit Status*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "*Local Tracking:*\n"
        f"  Per min: {escape_md(str(stats['minute_count']))}/{escape_md(str(stats['minute_limit']))}\n"
        f"  Per hour: {escape_md(str(stats['hour_count']))}/{escape_md(str(stats['hour_limit']))}\n"
        f"  Can submit: {'🟢 Yes' if stats['can_submit_now'] else '🔴 No'}\n"
    )

    if not stats["can_submit_now"]:
        msg += f"  Next available in: *{escape_md(str(int(stats['seconds_until_available'])))}s*\n"

    if rl_info and rl_info.limit is not None:
        msg += (
            "\n*API Response Headers:*\n"
            f"  Limit: {escape_md(str(rl_info.limit))}\n"
            f"  Remaining: {escape_md(str(rl_info.remaining))}\n"
            f"  Reset: {escape_md(str(rl_info.reset))}\n"
        )

    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


@authorized
async def handle_url_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain messages — auto-detect and submit URLs."""
    text = update.message.text.strip()
    urls = extract_urls(text)

    if not urls:
        return  # Not a URL, ignore silently

    if len(urls) == 1:
        await _process_single_url(update, urls[0], context)
    else:
        # Multiple URLs found — add all to queue
        campaign_id = context.user_data.get("default_campaign")
        added, duplicates = await db.add_bulk_to_queue(urls, campaign_id=campaign_id)
        scheduler.notify_new_item()

        msg = f"📦 Found *{escape_md(str(len(urls)))}* URLs\n"
        msg += f"✅ Queued: *{escape_md(str(added))}*"
        if duplicates > 0:
            msg += f" \\| ⚠️ Duplicates: *{escape_md(str(duplicates))}*"

        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)


# ─── Application Lifecycle ───────────────────────────────────────────────────

async def post_init(application: Application):
    """Called after the application is initialized."""
    global db, api, scheduler

    # Initialize database
    db = Database(config.db_path)
    await db.init()
    logger.info("Database initialized")

    # Initialize API client
    api = MonsterLabAPI(config.monsterlab_api_key, config.monsterlab_base_url)
    await api.__aenter__()
    logger.info("API client initialized")

    # Initialize rate limiter & scheduler
    rate_limiter = RateLimiter(
        per_minute=config.max_requests_per_minute,
        per_hour=config.max_requests_per_hour,
        min_interval=config.min_interval_seconds,
    )

    # Create notification callback
    async def notify_submission(queue_id: int, url: str, success: bool, result: dict):
        """Send Telegram notification when a queued submission completes."""
        try:
            if success:
                data = result.get("data", {})
                platform = data.get("platform", "unknown")
                emoji = PLATFORM_EMOJI.get(platform, "🔗")
                sub_id = data.get("submissionId", "")

                msg = (
                    f"✅ *Submitted Successfully*\n\n"
                    f"{emoji} `{escape_md(truncate(url, 50))}`\n"
                    f"🆔 `{escape_md(sub_id)}`\n"
                    f"📱 Platform: {escape_md(platform)}"
                )
            else:
                error = result.get("error", result.get("message", "Unknown error"))
                msg = (
                    f"❌ *Submission Failed*\n\n"
                    f"🔗 `{escape_md(truncate(url, 50))}`\n"
                    f"💬 {escape_md(str(error))}"
                )

            await application.bot.send_message(
                chat_id=config.authorized_user_id,
                text=msg,
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

    scheduler = SubmissionScheduler(
        api_client=api,
        database=db,
        rate_limiter=rate_limiter,
        on_submission=notify_submission,
    )
    await scheduler.start()
    logger.info("Scheduler started")

    # Auto-fetch campaigns and set default
    logger.info("Fetching campaigns...")
    if await refresh_campaigns():
        logger.info(f"Found {len(cached_campaigns)} campaign(s). Default: {default_campaign_id}")
    else:
        logger.warning("Could not fetch campaigns on startup. Use /campaigns later.")

    # Set bot commands for menu
    await application.bot.set_my_commands([
        BotCommand("start", "Welcome & quick start"),
        BotCommand("help", "Full command list"),
        BotCommand("submit", "Submit a clip URL"),
        BotCommand("bulk", "Bulk submit multiple URLs"),
        BotCommand("status", "Today's submission stats"),
        BotCommand("queue", "View pending queue"),
        BotCommand("history", "Recent submissions"),
        BotCommand("earnings", "Check your earnings"),
        BotCommand("campaigns", "List active campaigns"),
        BotCommand("setcampaign", "Set default campaign"),
        BotCommand("setpassword", "Set campaign password"),
        BotCommand("ratelimit", "Rate limit status"),
        BotCommand("cancel", "Cancel pending submissions"),
        BotCommand("validate", "Validate API key"),
    ])

    # Notify user that bot is ready with campaign selection
    try:
        if default_campaign_id and cached_campaigns:
            # Auto-selected a campaign — show confirmation with option to change
            camp_name = ""
            for c in cached_campaigns:
                if c.get("campaignId") == default_campaign_id:
                    camp_name = c.get("name", "")
                    break

            keyboard = build_campaign_keyboard()
            await application.bot.send_message(
                chat_id=config.authorized_user_id,
                text=(
                    f"🟢 Bot started!\n\n"
                    f"🎯 Auto-selected: {camp_name}\n\n"
                    f"Tap below to change campaign, or just paste a URL to submit!"
                ),
                reply_markup=keyboard,
            )
        elif cached_campaigns:
            # Campaigns exist but none auto-selected — show picker
            keyboard = build_campaign_keyboard()
            await application.bot.send_message(
                chat_id=config.authorized_user_id,
                text="🟢 Bot started!\n\n👇 Select a campaign to begin:",
                reply_markup=keyboard,
            )
        else:
            await application.bot.send_message(
                chat_id=config.authorized_user_id,
                text="🟢 Bot started!\n\n⚠️ No campaigns found. Use /campaigns to refresh.",
            )
    except Exception:
        pass

    logger.info("Bot is ready!")


async def post_shutdown(application: Application):
    """Called when the application shuts down."""
    global db, api, scheduler

    if scheduler:
        await scheduler.stop()
    if api:
        await api.__aexit__(None, None, None)
    if db:
        await db.close()

    logger.info("Bot shut down cleanly")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    """Entry point — create and run the bot."""
    global config

    # Load configuration
    config = load_config()
    logger.info(f"Config loaded. Base URL: {config.monsterlab_base_url}")

    # Build application
    app = (
        Application.builder()
        .token(config.telegram_bot_token)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Conversation handler for bulk mode
    bulk_handler = ConversationHandler(
        entry_points=[CommandHandler("bulk", cmd_bulk)],
        states={
            BULK_URLS: [
                CommandHandler("done", bulk_done),
                CommandHandler("cancel", cmd_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bulk_receive_urls),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
    )

    # Register handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("submit", cmd_submit))
    app.add_handler(bulk_handler)
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("queue", cmd_queue))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("earnings", cmd_earnings))
    app.add_handler(CommandHandler("campaigns", cmd_campaigns))
    app.add_handler(CommandHandler("setcampaign", cmd_setcampaign))
    app.add_handler(CommandHandler("setpassword", cmd_setpassword))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(CommandHandler("validate", cmd_validate))
    app.add_handler(CommandHandler("ratelimit", cmd_ratelimit))

    # Inline button callback handler for campaign selection
    app.add_handler(CallbackQueryHandler(callback_campaign_selected, pattern=r"^camp:"))

    # URL auto-detect handler — catches plain messages with URLs
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_message))

    logger.info("Starting bot polling...")
    app.run_polling(drop_pending_updates=True)


# ─── Health Check Server (for container platforms) ────────────────────────────

async def health_handler(request):
    """Simple health check endpoint for Choreo / container platforms."""
    return web.json_response({
        "status": "ok",
        "bot": "MonsterLab ClipIt Auto-Submit",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def start_health_server():
    """Start a lightweight HTTP server on port 8080 for health checks."""
    health_app = web.Application()
    health_app.router.add_get("/", health_handler)
    health_app.router.add_get("/health", health_handler)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(health_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server running on port {port}")


if __name__ == "__main__":
    # Start health check server in background, then run the bot
    loop = asyncio.new_event_loop()
    loop.run_until_complete(start_health_server())
    main()
