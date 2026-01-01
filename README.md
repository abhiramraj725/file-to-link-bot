# File-to-Link Telegram Bot 🔗

A Telegram bot that converts files into **instant download links**. Files up to 4GB supported!

## Features

- ⚡ **Instant link generation** - No waiting!
- 📦 Supports files up to 4GB (Telegram Premium)
- 🔗 Streaming download - no storage needed
- 🆓 100% free deployment on Koyeb

## Deploy to Koyeb

### 1. Fork/Push to GitHub

### 2. Create Koyeb Account
Go to [koyeb.com](https://koyeb.com) and sign up (free)

### 3. Deploy
1. Click **Create App** → **GitHub**
2. Select this repository
3. Set **Build command**: `pip install -r requirements.txt`
4. Set **Run command**: `python bot/streaming_bot.py`
5. Add environment variables:
   - `BOT_TOKEN` - Your bot token
   - `API_ID` - Your API ID
   - `API_HASH` - Your API Hash
   - `BASE_URL` - Your Koyeb app URL (e.g., `https://your-app.koyeb.app`)
6. Deploy!

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BOT_TOKEN` | Telegram bot token from @BotFather |
| `API_ID` | Telegram API ID from my.telegram.org |
| `API_HASH` | Telegram API Hash |
| `BASE_URL` | Public URL of your deployed app |

## Local Development

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python bot/streaming_bot.py
```

## License
MIT
