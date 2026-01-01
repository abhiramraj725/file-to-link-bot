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

from config import config

# Store file info: {file_hash: {file_id, file_name, file_size, access_hash, ...}}
file_cache = {}

# Bot client - use in_memory to avoid session conflicts
app = Client(
    name="file_to_link_bot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    in_memory=True,  # Don't save session to disk
)


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

# Debug: catch all messages (group -1 runs first, doesn't block others)
@app.on_message(group=-1)
async def debug_all_messages(client: Client, message: Message):
    """Log all incoming messages for debugging."""
    logger.info(f"Received message from {message.from_user.id if message.from_user else 'unknown'}: {message.text or message.media or 'Unknown'}")


@app.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    """Handle /start command."""
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


@app.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    """Handle /help command."""
    help_text = """
📖 **Help**

• Send any file to get a download link
• Links are generated instantly
• Maximum file size: 4GB (Telegram Premium)

**Supported:** Documents, Videos, Audio, Photos
    """
    await message.reply_text(help_text.strip())


@app.on_message(filters.document | filters.video | filters.audio | filters.voice | filters.video_note | filters.photo)
async def handle_file(client: Client, message: Message):
    """Handle incoming files - generate instant download link."""
    
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
        print(f"Streaming error: {e}")
    
    return response


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="OK")


async def start_web_server():
    """Start the web server for file streaming."""
    web_app = web.Application()
    web_app.router.add_get("/dl/{file_hash}/{file_name}", handle_download)
    web_app.router.add_get("/health", handle_health)
    
    runner = web.AppRunner(web_app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    print(f"🌐 Web server running on port {port}")
    return runner


async def main():
    """Start both bot and web server."""
    print("🚀 Starting File-to-Link Bot (Streaming Mode)...")
    
    # Create sessions directory
    os.makedirs("sessions", exist_ok=True)
    
    # Start web server
    runner = await start_web_server()
    
    # Start bot
    await app.start()
    print("✅ Bot is running! Press Ctrl+C to stop.")
    
    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        await app.stop()
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
