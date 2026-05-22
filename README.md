# 🧪 MonsterLab ClipIt Auto-Submit Telegram Bot

A free Telegram bot that automates clip/reel URL submissions to [MonsterLab.io](https://monsterlab.io)'s ClipIt platform. Submit clips from your phone, manage queues, track earnings — all from Telegram.

## ✨ Features

- **Auto-submit** — Just paste a URL and the bot submits it to MonsterLab
- **Bulk submit** — Send multiple URLs at once, the bot queues them all
- **Smart rate limiting** — Respects API limits (100/min, 6000/hr) automatically
- **Queue management** — View pending items, cancel, track progress
- **Earnings tracking** — Check your MonsterLab earnings from Telegram
- **Campaign browser** — List active campaigns and set defaults
- **Duplicate detection** — Never accidentally submit the same URL twice
- **Private & secure** — Only responds to your Telegram user ID

## 📋 Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message |
| `/help` | Full command list |
| `/submit <url>` | Submit a single clip URL |
| `/bulk` | Start bulk submission mode |
| `/status` | Today's submission stats |
| `/queue` | View pending queue |
| `/history [n]` | Recent submissions |
| `/earnings` | Check MonsterLab earnings |
| `/campaigns` | List active campaigns |
| `/setcampaign <id>` | Set default campaign |
| `/ratelimit` | Rate limit status |
| `/cancel` | Cancel pending submissions |
| `/validate` | Validate your API key |
| *(paste URL)* | Auto-detected and submitted |

## 🚀 Setup Guide

### Prerequisites
- Python 3.10 or higher
- A MonsterLab account with an API key
- A Telegram account

### Step 1: Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a name (e.g., "MonsterLab Submit Bot")
4. Choose a username (e.g., `my_monsterlab_bot`)
5. Copy the **Bot Token** — you'll need it

### Step 2: Get Your Telegram User ID

1. Search for **@userinfobot** on Telegram
2. Send `/start`
3. Copy your **User ID** (a number like `123456789`)

### Step 3: Get Your MonsterLab API Key

1. Log into [monsterlab.io](https://monsterlab.io)
2. Go to **Account & API** in the sidebar
3. Copy your API key (starts with `ml_`)

### Step 4: Configure the Bot

```bash
# Clone or navigate to the project
cd "d:\projects\ML autosubmit"

# Copy the example env file
copy .env.example .env

# Edit .env with your actual values
notepad .env
```

Fill in your `.env` file:
```
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
MONSTERLAB_API_KEY=ml_your_actual_api_key_here
AUTHORIZED_USER_ID=123456789
```

### Step 5: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 6: Run the Bot

```bash
python bot.py
```

You should see:
```
INFO - Config loaded. Base URL: https://monsterlab.io
INFO - Database initialized
INFO - API client initialized
INFO - Scheduler started
INFO - Bot is ready!
INFO - Starting bot polling...
```

Now go to Telegram and send `/start` to your bot! 🎉

---

## ☁️ Deploy to PythonAnywhere (Free)

PythonAnywhere offers a free tier that can run your bot 24/7.

### Step 1: Create Account

1. Go to [pythonanywhere.com](https://www.pythonanywhere.com)
2. Sign up for a **free Beginner account**

### Step 2: Upload Files

1. Go to the **Files** tab
2. Create a directory: `monsterlab_bot/`
3. Upload all project files:
   - `bot.py`, `config.py`, `monsterlab_api.py`, `database.py`
   - `scheduler.py`, `utils.py`, `requirements.txt`, `.env`

### Step 3: Install Dependencies

1. Go to the **Consoles** tab
2. Start a **Bash console**
3. Run:

```bash
cd monsterlab_bot
pip install --user -r requirements.txt
```

### Step 4: Set Up Always-On Task

1. Go to the **Tasks** tab
2. Under **Always-on tasks** (available on free tier for one task)
3. Enter the command:
```
python3 /home/YOUR_USERNAME/monsterlab_bot/bot.py
```
4. Click **Create**

> ⚠️ **Free tier note**: PythonAnywhere free accounts have limited outbound network access. Telegram Bot API works because it uses `api.telegram.org` which is allowed. However, `monsterlab.io` may need to be whitelisted. If you get connection errors, go to the **Consoles** tab and try:
> ```bash
> python3 -c "import requests; print(requests.get('https://monsterlab.io').status_code)"
> ```
> If it fails, you may need to upgrade to a paid plan ($5/mo) or use a different free hosting option.

### Alternative Free Hosting: Oracle Cloud

If PythonAnywhere doesn't work due to network restrictions:

1. Sign up at [cloud.oracle.com](https://cloud.oracle.com) (always-free tier)
2. Create a free **VM.Standard.E2.1.Micro** instance (Ubuntu)
3. SSH in and clone your project
4. Install Python 3.10+ and dependencies
5. Run with `nohup python3 bot.py &` or set up a systemd service

---

## 📁 Project Structure

```
ML autosubmit/
├── bot.py              # Main Telegram bot + command handlers
├── config.py           # Environment config loader
├── monsterlab_api.py   # MonsterLab ClipIt API client
├── database.py         # SQLite persistence layer
├── scheduler.py        # Rate-limit-aware submission queue
├── utils.py            # URL validation, formatting helpers
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .env                # Your actual config (DO NOT SHARE)
└── submissions.db      # SQLite database (auto-created)
```

## ⚠️ Important Notes

- **Rate Limits**: The bot conservatively limits to 80 req/min and 5000 req/hr (actual limits are 100/min, 6000/hr)
- **Duplicate Protection**: Each URL can only be submitted once. Failed URLs can be retried.
- **API Key Security**: Never share your `.env` file or API key
- **Terms of Service**: This bot submits clips through MonsterLab's official API. Always comply with their ToS.

## 🐛 Troubleshooting

**Bot doesn't respond**: Make sure `AUTHORIZED_USER_ID` matches your Telegram user ID

**API errors**: Run `/validate` to check your API key is valid

**Rate limit errors**: The bot auto-handles these. Check `/ratelimit` for status

**Connection errors on PythonAnywhere**: The free tier blocks some domains. Try Oracle Cloud instead.
