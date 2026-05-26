"""
MonsterLab ClipIt Auto-Submit Discord Bot

A Discord bot that automates clip URL submissions to MonsterLab.io's
ClipIt platform with rate limiting, bulk submissions, and earnings tracking.
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone

import discord
from discord import app_commands, Embed, Interaction, SelectOption
from discord.ui import Select, View
from aiohttp import web

from config import load_config, Config
from monsterlab_api import MonsterLabAPI
from database import Database
from scheduler import SubmissionScheduler, RateLimiter
from utils import (
    is_valid_url,
    detect_platform,
    extract_urls,
    format_time_ago,
    truncate,
    PLATFORM_EMOJIS as PLATFORM_EMOJI,
)

# ─── Logging Setup ───────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("discord").setLevel(logging.WARNING)
logging.getLogger("discord.http").setLevel(logging.WARNING)
logger = logging.getLogger("monsterlab_bot")

# ─── Globals ─────────────────────────────────────────────────────────────────

config: Config = None
db: Database = None
api: MonsterLabAPI = None
scheduler: SubmissionScheduler = None
cached_campaigns: list = []
default_campaign_id: str = None
campaign_passwords: dict = {}  # campaign_id -> password mapping
notification_channel_id: int = None  # channel to send submission results


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def refresh_campaigns():
    """Fetch campaigns from API and cache them. Auto-set default if needed."""
    global cached_campaigns, default_campaign_id
    try:
        result = await api.get_campaigns()
        if result.get("success"):
            cached_campaigns = result.get("data", [])
            if not default_campaign_id and cached_campaigns:
                default_campaign_id = cached_campaigns[0].get("campaignId")
                logger.info(f"Auto-selected campaign: {default_campaign_id} ({cached_campaigns[0].get('name')})")
            return True
    except Exception as e:
        logger.error(f"Failed to fetch campaigns: {e}")
    return False


def get_campaign_password(campaign_id: str | None) -> str | None:
    """Get the password for a campaign, if set."""
    if campaign_id:
        return campaign_passwords.get(campaign_id)
    return None


def is_authorized(interaction: Interaction) -> bool:
    """Check if the user is authorized."""
    return interaction.user.id == config.authorized_user_id


def unauthorized_embed() -> Embed:
    """Return an embed for unauthorized access."""
    return Embed(
        title="⛔ Unauthorized",
        description="This bot is private.",
        color=discord.Color.red(),
    )


# ─── Campaign Select Menu ───────────────────────────────────────────────────

class CampaignSelect(Select):
    """Dropdown menu for campaign selection."""

    def __init__(self, campaigns: list):
        options = []
        for camp in campaigns[:25]:  # Discord max 25 options
            camp_id = camp.get("campaignId", "")
            name = camp.get("name", "Unknown")
            desc = camp.get("description", "")
            is_default = camp_id == default_campaign_id
            options.append(SelectOption(
                label=truncate(name, 100),
                value=camp_id,
                description=truncate(desc, 100) if desc else None,
                default=is_default,
                emoji="✅" if is_default else "📌",
            ))
        super().__init__(
            placeholder="Select a campaign...",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: Interaction):
        global default_campaign_id

        if not is_authorized(interaction):
            await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
            return

        camp_id = self.values[0]
        default_campaign_id = camp_id

        # Find campaign name
        camp_name = camp_id
        for camp in cached_campaigns:
            if camp.get("campaignId") == camp_id:
                camp_name = camp.get("name", camp_id)
                break

        embed = Embed(
            title="✅ Campaign Selected!",
            description=f"**{camp_name}**\nID: `{camp_id}`\n\nAll submissions will now use this campaign.\nJust paste a URL to submit! 🚀",
            color=discord.Color.green(),
        )
        await interaction.response.edit_message(embed=embed, view=None)
        logger.info(f"Campaign selected via dropdown: {camp_id} ({camp_name})")


class CampaignView(View):
    """View containing the campaign select dropdown."""

    def __init__(self, campaigns: list):
        super().__init__(timeout=120)
        self.add_item(CampaignSelect(campaigns))


# ─── Discord Bot Class ───────────────────────────────────────────────────────

class MonsterLabBot(discord.Client):
    """Custom Discord client with app commands."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # needed for URL auto-detection
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        """Register slash commands on startup."""
        await self.tree.sync()
        logger.info("Slash commands synced")


bot = MonsterLabBot()


# ─── Slash Commands ──────────────────────────────────────────────────────────

@bot.tree.command(name="start", description="Welcome message and quick start guide")
async def cmd_start(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    embed = Embed(
        title="🧪 MONSTERLAB ClipIt Auto-Submit Bot",
        description=(
            "Submit your social media clips to MonsterLab automatically!\n\n"
            "**📋 Quick Start:**\n"
            "• Paste any clip URL in chat to auto-submit\n"
            "• `/submit` - Submit a single clip\n"
            "• `/bulk` - Submit multiple URLs at once\n"
            "• `/status` - View today's stats\n"
            "• `/earnings` - Check your earnings\n"
            "• `/help` - Full command list\n\n"
            "💡 *Just paste a URL and I'll handle the rest!*"
        ),
        color=discord.Color.purple(),
    )
    embed.set_footer(text="MonsterLab ClipIt Bot")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show all available commands")
async def cmd_help(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    embed = Embed(
        title="🧪 MONSTERLAB Bot - Commands",
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="📤 Submission",
        value=(
            "`/submit` - Submit a single clip URL\n"
            "`/bulk` - Submit multiple URLs\n"
            "`/setcampaign` - Set default campaign\n"
            "`/setpassword` - Set campaign password"
        ),
        inline=False,
    )
    embed.add_field(
        name="📊 Monitoring",
        value=(
            "`/status` - Today's submission stats\n"
            "`/queue` - View pending queue\n"
            "`/history` - Recent submissions\n"
            "`/earnings` - Check earnings\n"
            "`/campaigns` - List active campaigns\n"
            "`/ratelimit` - Rate limit status"
        ),
        inline=False,
    )
    embed.add_field(
        name="🛠 Management",
        value=(
            "`/cancel` - Cancel all pending submissions\n"
            "`/validate` - Validate your API key"
        ),
        inline=False,
    )
    embed.set_footer(text="💡 Tip: Just paste a URL (no command needed) and I'll auto-detect and submit it!")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="submit", description="Submit a single clip URL")
@app_commands.describe(url="The clip URL to submit (TikTok, Instagram, YouTube, etc.)")
async def cmd_submit(interaction: Interaction, url: str):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()
    await _process_single_url(interaction, url.strip())


async def _process_single_url(interaction: Interaction, url: str):
    """Process and queue a single URL for submission."""
    global notification_channel_id

    if not is_valid_url(url):
        if not url.startswith("http"):
            url = "https://" + url
        if not is_valid_url(url):
            embed = Embed(
                title="❌ Invalid URL",
                description=f"`{truncate(url, 60)}`\n\nPlease provide a valid HTTP/HTTPS URL.",
                color=discord.Color.red(),
            )
            await interaction.followup.send(embed=embed)
            return

    platform = detect_platform(url)
    emoji = PLATFORM_EMOJI.get(platform or "unknown", "🔗")

    campaign_id = default_campaign_id

    if not campaign_id:
        await refresh_campaigns()
        campaign_id = default_campaign_id

    if not campaign_id:
        if cached_campaigns:
            view = CampaignView(cached_campaigns)
            embed = Embed(
                title="⚠️ No Campaign Selected",
                description="Select a campaign from the dropdown below:",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed, view=view)
        else:
            embed = Embed(
                title="⚠️ No Campaigns Found",
                description="Run `/campaigns` to refresh the list.",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed)
        return

    try:
        campaign_pw = get_campaign_password(campaign_id)
        queue_id = await db.add_to_queue(url, campaign_id=campaign_id, password=campaign_pw)
        scheduler.notify_new_item()

        # Remember channel for notifications
        notification_channel_id = interaction.channel_id

        pending = await db.get_queue_count()
        rate_stats = scheduler.rate_limiter.get_stats()

        embed = Embed(
            title="⏳ Queued for Submission",
            color=discord.Color.blue(),
        )
        embed.add_field(name="URL", value=f"{emoji} `{truncate(url, 55)}`", inline=False)
        embed.add_field(name="Campaign", value=f"🎯 `{campaign_id}`", inline=True)
        embed.add_field(name="Queue Position", value=f"📍 **{pending}**", inline=True)

        if rate_stats["can_submit_now"]:
            embed.add_field(name="Status", value="🚀 Submitting shortly...", inline=False)
        else:
            wait = rate_stats["seconds_until_available"]
            embed.add_field(name="Status", value=f"⏱ Rate limit: ~{int(wait)}s wait", inline=False)

        await interaction.followup.send(embed=embed)

    except Exception as e:
        embed = Embed(
            title="❌ Error",
            description=f"Failed to queue: {str(e)}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="bulk", description="Submit multiple URLs at once")
@app_commands.describe(urls="Paste your URLs, one per line")
async def cmd_bulk(interaction: Interaction, urls: str):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()
    global notification_channel_id
    notification_channel_id = interaction.channel_id

    # Parse URLs from the input
    parsed_urls = extract_urls(urls)

    # Also try line-by-line for URLs without http
    if not parsed_urls:
        lines = [line.strip() for line in urls.split("\n") if line.strip()]
        for line in lines:
            if not line.startswith("http"):
                line = "https://" + line
            if is_valid_url(line):
                parsed_urls.append(line)

    if not parsed_urls:
        embed = Embed(
            title="⚠️ No Valid URLs Found",
            description="Please provide valid URLs, one per line.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)
        return

    campaign_id = default_campaign_id

    if not campaign_id:
        await refresh_campaigns()
        campaign_id = default_campaign_id

    if not campaign_id:
        embed = Embed(
            title="⚠️ No Campaign Selected",
            description="Run `/campaigns` to select a campaign first.",
            color=discord.Color.orange(),
        )
        await interaction.followup.send(embed=embed)
        return

    campaign_pw = get_campaign_password(campaign_id)
    added, duplicates = await db.add_bulk_to_queue(parsed_urls, campaign_id=campaign_id, password=campaign_pw)
    scheduler.notify_new_item()

    pending = await db.get_queue_count()

    embed = Embed(
        title="📦 Bulk Submission Complete",
        color=discord.Color.green(),
    )
    embed.add_field(name="✅ Queued", value=f"**{added}** clips", inline=True)
    if duplicates > 0:
        embed.add_field(name="⚠️ Duplicates Skipped", value=f"**{duplicates}**", inline=True)
    embed.add_field(name="📍 Total in Queue", value=f"**{pending}**", inline=True)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="status", description="Show today's submission stats")
async def cmd_status(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()

    stats = await db.get_today_stats()
    queue_status = await scheduler.get_queue_status()
    rate = queue_status["rate_limit"]

    embed = Embed(
        title="📊 Today's Stats",
        color=discord.Color.teal(),
    )
    embed.add_field(name="✅ Submitted", value=f"**{stats['submitted']}**", inline=True)
    embed.add_field(name="⏳ Pending", value=f"**{stats['pending']}**", inline=True)
    embed.add_field(name="❌ Failed", value=f"**{stats['failed']}**", inline=True)
    embed.add_field(name="📈 Total", value=f"**{stats['total']}**", inline=True)
    embed.add_field(
        name="⚡ Rate Limits",
        value=f"Per min: {rate['minute_count']}/{rate['minute_limit']}\nPer hour: {rate['hour_count']}/{rate['hour_limit']}",
        inline=False,
    )

    if queue_status["eta_seconds"] > 0:
        mins = int(queue_status["eta_seconds"] // 60)
        secs = int(queue_status["eta_seconds"] % 60)
        embed.add_field(name="⏱ Est. Completion", value=f"~{mins}m {secs}s", inline=False)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="queue", description="View pending submission queue")
async def cmd_queue(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()

    queue_status = await scheduler.get_queue_status()
    pending = queue_status["pending"]

    if pending == 0:
        embed = Embed(
            title="📭 Queue Empty",
            description="Send a URL to get started!",
            color=discord.Color.light_grey(),
        )
        await interaction.followup.send(embed=embed)
        return

    rate = queue_status["rate_limit"]
    embed = Embed(
        title="📬 Submission Queue",
        color=discord.Color.blue(),
    )
    embed.add_field(name="⏳ Pending", value=f"**{pending}** clips", inline=True)
    embed.add_field(
        name="🏃 Scheduler",
        value="🟢 Running" if queue_status["is_running"] else "🔴 Stopped",
        inline=True,
    )

    if rate["can_submit_now"]:
        embed.add_field(name="🚀 Status", value="**Submitting now**", inline=False)
    else:
        wait = rate["seconds_until_available"]
        embed.add_field(name="⏱ Next Submit", value=f"In **{int(wait)}s**", inline=False)

    if queue_status["eta_seconds"] > 0:
        mins = int(queue_status["eta_seconds"] // 60)
        secs = int(queue_status["eta_seconds"] % 60)
        embed.add_field(name="📍 Est. Completion", value=f"~{mins}m {secs}s", inline=False)

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="history", description="Show recent submissions")
@app_commands.describe(limit="Number of submissions to show (max 25)")
async def cmd_history(interaction: Interaction, limit: int = 10):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()
    limit = min(max(limit, 1), 25)

    submissions = await db.get_recent_submissions(limit)

    if not submissions:
        embed = Embed(
            title="📭 No Submissions Yet",
            description="Submit a URL to get started!",
            color=discord.Color.light_grey(),
        )
        await interaction.followup.send(embed=embed)
        return

    embed = Embed(
        title=f"📜 Last {len(submissions)} Submissions",
        color=discord.Color.blue(),
    )

    lines = []
    for sub in submissions:
        platform = sub.get("platform", "unknown")
        emoji = PLATFORM_EMOJI.get(platform, "🔗")
        status_emoji = {"success": "✅", "failed": "❌", "pending": "⏳"}.get(sub["status"], "❓")

        url_display = truncate(sub["url"], 40)
        time_str = ""
        if sub.get("submitted_at"):
            try:
                dt = datetime.fromisoformat(sub["submitted_at"])
                time_str = f" - {format_time_ago(dt)}"
            except (ValueError, TypeError):
                pass

        sub_id = sub.get("submission_id", "")
        id_str = f" `{sub_id}`" if sub_id else ""

        lines.append(f"{status_emoji} {emoji} `{url_display}`{id_str}{time_str}")

    embed.description = "\n".join(lines)
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="earnings", description="Check your MonsterLab earnings")
async def cmd_earnings(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()

    try:
        result = await api.get_account_info()

        if result.get("success"):
            data = result.get("data", {})
            est_total = data.get("estimatedEarnings", data.get("earnings", {}).get("total", "N/A"))
            pending = data.get("pendingEarnings", data.get("earnings", {}).get("pending", "N/A"))
            available = data.get("availableEarnings", data.get("earnings", {}).get("available", "N/A"))

            embed = Embed(
                title="💰 MonsterLab Earnings",
                color=discord.Color.gold(),
            )
            embed.add_field(name="📊 Est. Total", value=f"**${est_total}**", inline=True)
            embed.add_field(name="⏳ Pending", value=f"**${pending}**", inline=True)
            embed.add_field(name="✅ Available", value=f"**${available}**", inline=True)

            await interaction.followup.send(embed=embed)
        else:
            embed = Embed(
                title="⚠️ Could Not Fetch Earnings",
                description=f"{result.get('error', 'Unknown error')}\n\nCheck your MonsterLab dashboard directly.",
                color=discord.Color.orange(),
            )
            await interaction.followup.send(embed=embed)
    except Exception as e:
        embed = Embed(
            title="❌ Error",
            description=f"Failed to fetch earnings: {str(e)}",
            color=discord.Color.red(),
        )
        await interaction.followup.send(embed=embed)


@bot.tree.command(name="campaigns", description="List active campaigns and select one")
async def cmd_campaigns(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()
    await refresh_campaigns()

    if not cached_campaigns:
        embed = Embed(
            title="📭 No Active Campaigns",
            description="No campaigns found on MonsterLab.",
            color=discord.Color.light_grey(),
        )
        await interaction.followup.send(embed=embed)
        return

    embed = Embed(
        title=f"🎯 Active Campaigns ({len(cached_campaigns)})",
        color=discord.Color.purple(),
    )

    for camp in cached_campaigns[:10]:
        name = camp.get("name", "Unknown")
        camp_id = camp.get("campaignId", "")
        desc = camp.get("description", "")
        is_active = camp_id == default_campaign_id

        marker = "✅" if is_active else "📌"
        value_parts = []

        if desc:
            value_parts.append(truncate(desc, 80))

        # Payout rates
        rates = camp.get("payoutRates", {})
        if rates:
            rate_parts = []
            for platform, rate in rates.items():
                p_emoji = PLATFORM_EMOJI.get(platform, "")
                rate_parts.append(f"{p_emoji}${rate}")
            value_parts.append("💵 " + " | ".join(rate_parts))

        value_parts.append(f"ID: `{camp_id}`")

        field_name = f"{marker} {name}"
        if is_active:
            field_name += " (selected)"

        embed.add_field(
            name=field_name,
            value="\n".join(value_parts) if value_parts else "No details",
            inline=False,
        )

    embed.set_footer(text="👇 Select a campaign from the dropdown below:")

    view = CampaignView(cached_campaigns)
    await interaction.followup.send(embed=embed, view=view)


@bot.tree.command(name="setcampaign", description="Set default campaign for submissions")
@app_commands.describe(campaign_id="Campaign ID (e.g., camp_123456). Use 'clear' to remove override.")
async def cmd_setcampaign(interaction: Interaction, campaign_id: str):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    global default_campaign_id

    campaign_id = campaign_id.strip()
    if campaign_id.lower() == "clear":
        default_campaign_id = None
        embed = Embed(
            title="✅ Campaign Cleared",
            description="No default campaign set. Use `/campaigns` to select one.",
            color=discord.Color.green(),
        )
    else:
        default_campaign_id = campaign_id
        embed = Embed(
            title="✅ Campaign Set",
            description=f"Default campaign: `{campaign_id}`",
            color=discord.Color.green(),
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="setpassword", description="Set password for the current campaign")
@app_commands.describe(
    password="Campaign password (use 'clear' to remove)",
    campaign_id="Optional: specific campaign ID (defaults to current)",
)
async def cmd_setpassword(interaction: Interaction, password: str, campaign_id: str = None):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    global campaign_passwords

    target_camp = campaign_id or default_campaign_id

    if password.lower() == "clear":
        if target_camp and target_camp in campaign_passwords:
            del campaign_passwords[target_camp]
            embed = Embed(
                title="🔓 Password Cleared",
                description=f"Password removed for campaign: `{target_camp}`",
                color=discord.Color.green(),
            )
        else:
            embed = Embed(
                title="🔓 No Password Set",
                description="There was no password to clear.",
                color=discord.Color.light_grey(),
            )
    else:
        if not target_camp:
            embed = Embed(
                title="⚠️ No Campaign Selected",
                description="Select a campaign first with `/campaigns`",
                color=discord.Color.orange(),
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        campaign_passwords[target_camp] = password
        embed = Embed(
            title="🔒 Password Set",
            description=f"Password set for campaign: `{target_camp}`\nAll submissions will include it.",
            color=discord.Color.green(),
        )

    logger.info(f"Campaign passwords updated: {len(campaign_passwords)} campaign(s) have passwords")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="cancel", description="Cancel all pending submissions")
async def cmd_cancel(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()
    cancelled = await db.cancel_all_pending()

    if cancelled == 0:
        embed = Embed(
            title="📭 Nothing to Cancel",
            description="No pending submissions in the queue.",
            color=discord.Color.light_grey(),
        )
    else:
        embed = Embed(
            title="🗑 Submissions Cancelled",
            description=f"Cancelled **{cancelled}** pending submission(s).",
            color=discord.Color.orange(),
        )

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="validate", description="Validate your MonsterLab API key")
async def cmd_validate(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    await interaction.response.defer()

    try:
        result = await api.validate_key()

        if result:
            embed = Embed(
                title="✅ API Key Valid",
                description=f"Key: `{config.monsterlab_api_key[:8]}...`\nConnection to MonsterLab is working!",
                color=discord.Color.green(),
            )
        else:
            embed = Embed(
                title="❌ API Key Invalid",
                description="Your MonsterLab API key was rejected. Check your key and try again.",
                color=discord.Color.red(),
            )
    except Exception as e:
        embed = Embed(
            title="❌ Validation Error",
            description=f"Error: {str(e)}",
            color=discord.Color.red(),
        )

    await interaction.followup.send(embed=embed)


@bot.tree.command(name="ratelimit", description="Show current rate limit status")
async def cmd_ratelimit(interaction: Interaction):
    if not is_authorized(interaction):
        await interaction.response.send_message(embed=unauthorized_embed(), ephemeral=True)
        return

    stats = scheduler.rate_limiter.get_stats()

    embed = Embed(
        title="⚡ Rate Limit Status",
        color=discord.Color.teal(),
    )
    embed.add_field(
        name="Per Minute",
        value=f"{stats['minute_count']}/{stats['minute_limit']}",
        inline=True,
    )
    embed.add_field(
        name="Per Hour",
        value=f"{stats['hour_count']}/{stats['hour_limit']}",
        inline=True,
    )
    embed.add_field(
        name="Can Submit Now",
        value="🟢 Yes" if stats["can_submit_now"] else "🔴 No",
        inline=True,
    )

    if not stats["can_submit_now"]:
        embed.add_field(
            name="⏱ Next Available",
            value=f"In {stats['seconds_until_available']}s",
            inline=False,
        )

    await interaction.response.send_message(embed=embed)


# ─── Auto-detect URLs in messages ────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    """Detect URLs in regular messages and auto-submit them."""
    # Ignore bot's own messages
    if message.author.id == bot.user.id:
        return

    # Only process from authorized user
    if message.author.id != config.authorized_user_id:
        return

    # Don't process if it starts with / (slash command)
    if message.content.startswith("/"):
        return

    # Extract URLs from the message
    urls = extract_urls(message.content)

    if not urls:
        return

    global notification_channel_id
    notification_channel_id = message.channel.id

    campaign_id = default_campaign_id

    if not campaign_id:
        await refresh_campaigns()
        campaign_id = default_campaign_id

    if not campaign_id:
        if cached_campaigns:
            view = CampaignView(cached_campaigns)
            embed = Embed(
                title="⚠️ No Campaign Selected",
                description="Select a campaign from the dropdown below:",
                color=discord.Color.orange(),
            )
            await message.reply(embed=embed, view=view)
        else:
            await message.reply("⚠️ No campaigns found! Run `/campaigns` to refresh.")
        return

    # Process each URL
    queued = 0
    errors = []
    for url in urls:
        try:
            campaign_pw = get_campaign_password(campaign_id)
            await db.add_to_queue(url, campaign_id=campaign_id, password=campaign_pw)
            queued += 1
        except Exception as e:
            errors.append(f"`{truncate(url, 40)}`: {str(e)}")

    scheduler.notify_new_item()

    if queued > 0:
        pending = await db.get_queue_count()
        platform = detect_platform(urls[0]) if len(urls) == 1 else None
        emoji = PLATFORM_EMOJI.get(platform or "unknown", "🔗")

        embed = Embed(
            title="⏳ Queued for Submission",
            color=discord.Color.blue(),
        )

        if len(urls) == 1:
            embed.add_field(name="URL", value=f"{emoji} `{truncate(urls[0], 55)}`", inline=False)
        else:
            embed.add_field(name="URLs", value=f"**{queued}** clip(s) queued", inline=False)

        embed.add_field(name="Campaign", value=f"🎯 `{campaign_id}`", inline=True)
        embed.add_field(name="Queue Position", value=f"📍 **{pending}**", inline=True)

        rate_stats = scheduler.rate_limiter.get_stats()
        if rate_stats["can_submit_now"]:
            embed.add_field(name="Status", value="🚀 Submitting shortly...", inline=False)

        await message.reply(embed=embed)

    if errors:
        error_text = "\n".join(errors[:5])
        embed = Embed(
            title="⚠️ Some URLs Failed",
            description=error_text,
            color=discord.Color.orange(),
        )
        await message.channel.send(embed=embed)


# ─── Submission Result Notifications ─────────────────────────────────────────

async def on_submission_complete(queue_id: int, url: str, success: bool, result: dict):
    """Called by scheduler when a submission completes. Sends Discord notification."""
    if not notification_channel_id:
        return

    try:
        channel = bot.get_channel(notification_channel_id)
        if not channel:
            channel = await bot.fetch_channel(notification_channel_id)

        if not channel:
            return

        platform = detect_platform(url)
        emoji = PLATFORM_EMOJI.get(platform or "unknown", "🔗")

        if success:
            data = result.get("data", {})
            sub_id = data.get("submissionId", "N/A")

            embed = Embed(
                title="✅ Submission Successful",
                color=discord.Color.green(),
            )
            embed.add_field(name="URL", value=f"{emoji} `{truncate(url, 55)}`", inline=False)
            embed.add_field(name="Submission ID", value=f"`{sub_id}`", inline=True)
            embed.add_field(name="Platform", value=data.get("platform", "unknown").title(), inline=True)
        else:
            error_msg = result.get("error", result.get("message", "Unknown error"))

            embed = Embed(
                title="❌ Submission Failed",
                color=discord.Color.red(),
            )
            embed.add_field(name="URL", value=f"{emoji} `{truncate(url, 55)}`", inline=False)
            embed.add_field(name="Error", value=f"```{truncate(str(error_msg), 200)}```", inline=False)

        await channel.send(embed=embed)

    except Exception as e:
        logger.error(f"Failed to send notification: {e}")


# ─── Health Check Server ─────────────────────────────────────────────────────

async def health_handler(request: web.Request) -> web.Response:
    """Simple health check endpoint for container platforms."""
    return web.Response(text="OK", status=200)


async def start_health_server():
    """Start the aiohttp health check server on port 8080."""
    app = web.Application()
    app.router.add_get("/health", health_handler)
    app.router.add_get("/", health_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()
    logger.info("Health check server running on port 8080")


# ─── Bot Startup ─────────────────────────────────────────────────────────────

@bot.event
async def on_ready():
    """Called when the bot is ready and connected to Discord."""
    global config, db, api, scheduler

    logger.info(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    logger.info(f"Connected to {len(bot.guilds)} guild(s)")

    # Start health check server
    await start_health_server()

    # Initialize database
    db_path = os.getenv("DB_PATH", "submissions.db")
    db = Database(db_path)
    await db.init()
    logger.info("Database initialized")

    # Initialize API client
    api = MonsterLabAPI(
        api_key=config.monsterlab_api_key,
        base_url=config.monsterlab_base_url,
    )
    await api.__aenter__()  # Open the aiohttp session
    logger.info("API client initialized")

    # Initialize scheduler
    rate_limiter = RateLimiter(
        per_minute=config.max_requests_per_minute,
        per_hour=config.max_requests_per_hour,
        min_interval=config.min_interval_seconds,
    )
    scheduler = SubmissionScheduler(
        api_client=api,
        database=db,
        rate_limiter=rate_limiter,
        on_submission=on_submission_complete,
    )
    await scheduler.start()
    logger.info("Scheduler started")

    # Fetch campaigns
    await refresh_campaigns()
    if cached_campaigns:
        logger.info(f"Found {len(cached_campaigns)} campaign(s). Default: {default_campaign_id}")

    logger.info("Bot is ready! 🚀")


# ─── Main Entry Point ───────────────────────────────────────────────────────

def main():
    global config

    logger.info("Starting bot...")

    # Load config
    config = load_config()
    logger.info(f"Config loaded. Base URL: {config.monsterlab_base_url}")

    # Validate API key format
    logger.info(f"Validating API key {config.monsterlab_api_key[:8]}...")

    # Run the bot
    bot.run(config.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
