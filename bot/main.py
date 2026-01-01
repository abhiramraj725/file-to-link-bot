"""Main entry point for the File-to-Link Telegram Bot."""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pyrogram import Client

from config import config
from bot.handlers import BotHandlers


def create_app() -> Client:
    """Create and configure the Pyrogram client."""
    app = Client(
        name="file_to_link_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        workdir="./sessions",
    )
    return app


def main():
    """Start the bot."""
    print("🚀 Starting File-to-Link Bot...")
    print("📦 Using Gofile.io for file storage (FREE, no account needed)")
    
    # Create sessions directory
    os.makedirs("sessions", exist_ok=True)
    
    # Initialize components
    app = create_app()
    
    # Register handlers
    BotHandlers(app)
    
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    # Start the bot
    app.run()


if __name__ == "__main__":
    main()
