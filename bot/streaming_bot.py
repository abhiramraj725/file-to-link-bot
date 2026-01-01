"""
File-to-Link Telegram Bot with Streaming Proxy

This bot generates INSTANT download links by creating a streaming proxy server
that serves files directly from Telegram's servers. No download/upload wait!
"""

import os
import sys
import asyncio
import hashlib
import time
import logging
import threading
from urllib.parse import quote

# Enable logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiohttp import web
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.handlers import MessageHandler

from config import config

# Store file info: {file_hash: {file_id, file_name, file_size, access_hash, ...}}
file_cache = {}

# Bot client will be initialized later
app = None


def generate_file_hash(file_id: str) -> str:
    """Generate a short unique hash for the file."""
    return hashlib.md5(file_id.encode()).hexdigest()[:12]


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"


# ============== Telegram Bot Handlers ==============

async def start_command(client: Client, message: Message):
    """Handle /start command."""
    logger.info(f"Received /start from {message.from_user.id}")
    welcome_text = """
🔗 **File-to-Link Bot**

Send me any file and get an **instant download link**!

✨ **Features:**
• Instant link generation (no waiting!)
• Supports files up to 4GB
• Links work as long as the bot is running

Just send me a file to get started!
    """
    await message.reply_text(welcome_text.strip())


async def help_command(client: Client, message: Message):
    """Handle /help command."""
    logger.info(f"Received /help from {message.from_user.id}")
    help_text = """
📖 **Help**

• Send any file to get a download link
• Links are generated instantly
• Maximum file size: 4GB (Telegram Premium)

**Supported:** Documents, Videos, Audio, Photos
    """
    await message.reply_text(help_text.strip())


async def handle_file(client: Client, message: Message):
    """Handle incoming files - generate instant download link."""
    logger.info(f"Received file from {message.from_user.id}")
    
    # Get file info based on message type
    if message.document:
        file = message.document
        file_name = file.file_name or f"document_{file.file_unique_id}"
        file_size = file.file_size
        file_id = file.file_id
        mime_type = file.mime_type or "application/octet-stream"
    elif message.video:
        file = message.video
        file_name = file.file_name or f"video_{file.file_unique_id}.mp4"
        file_size = file.file_size
        file_id = file.file_id
        mime_type = file.mime_type or "video/mp4"
    elif message.audio:
        file = message.audio
        file_name = file.file_name or f"audio_{file.file_unique_id}.mp3"
        file_size = file.file_size
        file_id = file.file_id
        mime_type = file.mime_type or "audio/mpeg"
    elif message.voice:
        file = message.voice
        file_name = f"voice_{file.file_unique_id}.ogg"
        file_size = file.file_size
        file_id = file.file_id
        mime_type = file.mime_type or "audio/ogg"
    elif message.video_note:
        file = message.video_note
        file_name = f"video_note_{file.file_unique_id}.mp4"
        file_size = file.file_size
        file_id = file.file_id
        mime_type = "video/mp4"
    elif message.photo:
        file = message.photo
        file_name = f"photo_{file.file_unique_id}.jpg"
        file_size = file.file_size
        file_id = file.file_id
        mime_type = "image/jpeg"
    else:
        return
    
    # Generate hash and store file info
    file_hash = generate_file_hash(file_id)
    file_cache[file_hash] = {
        "file_id": file_id,
        "file_name": file_name,
        "file_size": file_size,
        "mime_type": mime_type,
        "created_at": time.time(),
    }
    
    # Generate download URL
    base_url = config.BASE_URL.rstrip("/")
    encoded_name = quote(file_name)
    download_url = f"{base_url}/dl/{file_hash}/{encoded_name}"
    
    size_str = format_size(file_size)
    
    await message.reply_text(
        f"✅ **Link Generated!**\n\n"
        f"📄 **File:** `{file_name}`\n"
        f"📊 **Size:** {size_str}\n\n"
        f"🔗 **Download Link:**\n{download_url}"
    )


# ============== Web Server for Streaming ==============

async def handle_download(request: web.Request) -> web.StreamResponse:
    """Handle file download requests - stream directly from Telegram."""
    global app
    file_hash = request.match_info.get("file_hash")
    
    if file_hash not in file_cache:
        return web.Response(text="File not found or link expired", status=404)
    
    file_info = file_cache[file_hash]
    file_id = file_info["file_id"]
    file_name = file_info["file_name"]
    file_size = file_info["file_size"]
    mime_type = file_info["mime_type"]
    
    # Create streaming response
    response = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": mime_type,
            "Content-Disposition": f'attachment; filename="{file_name}"',
            "Content-Length": str(file_size),
            "Accept-Ranges": "bytes",
        }
    )
    await response.prepare(request)
    
    try:
        # Stream file directly from Telegram
        async for chunk in app.stream_media(file_id):
            await response.write(chunk)
    except Exception as e:
        logger.error(f"Streaming error: {e}")
    
    return response


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="OK")


def run_web_server():
    """Run the web server in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_server():
        web_app = web.Application()
        web_app.router.add_get("/dl/{file_hash}/{file_name}", handle_download)
        web_app.router.add_get("/health", handle_health)
        
        runner = web.AppRunner(web_app)
        await runner.setup()
        
        port = int(os.getenv("PORT", 8080))
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Web server listening on port {port}")
        
        # Keep running forever
        while True:
            await asyncio.sleep(3600)
    
    loop.run_until_complete(start_server())


def main():
    """Start the bot."""
    global app
    
    print("🚀 Starting File-to-Link Bot (Streaming Mode)...")
    logger.info("Initializing bot...")
    
    # Create bot client
    app = Client(
        name="file_to_link_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        in_memory=True,
    )
    
    # Register handlers
    app.add_handler(MessageHandler(start_command, filters.command("start")))
    app.add_handler(MessageHandler(help_command, filters.command("help")))
    app.add_handler(MessageHandler(
        handle_file,
        filters.document | filters.video | filters.audio | filters.voice | filters.video_note | filters.photo
    ))
    
    # Start web server in background thread
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    print("🌐 Web server started in background")
    
    # Run the bot with FloodWait handling
    print("✅ Bot is starting...")
    while True:
        try:
            app.run()
            break
        except Exception as e:
            if "FloodWait" in str(type(e).__name__) or "FLOOD_WAIT" in str(e):
                wait_time = getattr(e, 'value', 60) if hasattr(e, 'value') else 60
                logger.warning(f"FloodWait: Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time + 5)
            else:
                logger.error(f"Error: {e}")
                raise


if __name__ == "__main__":
    main()

