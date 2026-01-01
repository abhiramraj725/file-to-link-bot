"""
File-to-Link Telegram Bot with Server-Side Download

This bot downloads files to the server first, then serves them as static files
for fast download speeds. Files are cached on the server.
"""

import os
import sys
import asyncio
import hashlib
import time
import logging
import threading
from urllib.parse import quote
from pathlib import Path

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

# Store file info: {file_hash: {file_id, file_name, file_size, local_path, ...}}
file_cache = {}

# Directory to store downloaded files
DOWNLOAD_DIR = Path("/tmp/telegram_files")
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

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

Send me any file and get a **fast download link**!

✨ **Features:**
• Fast download speeds (files cached on server)
• Supports files up to 2GB
• Resume downloads supported
• Links work as long as file is cached

Just send me a file to get started!
    """
    await message.reply_text(welcome_text.strip())


async def help_command(client: Client, message: Message):
    """Handle /help command."""
    logger.info(f"Received /help from {message.from_user.id}")
    help_text = """
📖 **Help**

• Send any file to get a download link
• Small files: Instant link
• Large files: Brief download wait, then fast link
• Maximum file size: 2GB

**Supported:** Documents, Videos, Audio, Photos
    """
    await message.reply_text(help_text.strip())


async def handle_file(client: Client, message: Message):
    """Handle incoming files - download to server and generate link."""
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
    
    file_hash = generate_file_hash(file_id)
    size_str = format_size(file_size)
    
    # Check if already cached
    if file_hash in file_cache and file_cache[file_hash].get("local_path"):
        local_path = Path(file_cache[file_hash]["local_path"])
        if local_path.exists():
            base_url = config.BASE_URL.rstrip("/")
            encoded_name = quote(file_name)
            download_url = f"{base_url}/dl/{file_hash}/{encoded_name}"
            
            await message.reply_text(
                f"✅ **Link Ready (Cached)!**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"📊 **Size:** {size_str}\n\n"
                f"🔗 **Download Link:**\n{download_url}"
            )
            return
    
    # Send processing message
    status_msg = await message.reply_text(
        f"⏳ **Downloading to server...**\n\n"
        f"📄 **File:** `{file_name}`\n"
        f"📊 **Size:** {size_str}\n\n"
        f"Please wait, this will only take a moment..."
    )
    
    try:
        # Download file to server
        local_path = DOWNLOAD_DIR / f"{file_hash}_{file_name}"
        
        # Use Pyrogram's download method for faster download
        await client.download_media(
            message,
            file_name=str(local_path)
        )
        
        # Store in cache
        file_cache[file_hash] = {
            "file_id": file_id,
            "file_name": file_name,
            "file_size": file_size,
            "mime_type": mime_type,
            "local_path": str(local_path),
            "created_at": time.time(),
        }
        
        # Generate download URL
        base_url = config.BASE_URL.rstrip("/")
        encoded_name = quote(file_name)
        download_url = f"{base_url}/dl/{file_hash}/{encoded_name}"
        
        await status_msg.edit_text(
            f"✅ **Link Generated!**\n\n"
            f"📄 **File:** `{file_name}`\n"
            f"📊 **Size:** {size_str}\n\n"
            f"🔗 **Download Link:**\n{download_url}\n\n"
            f"⚡ **Fast download from server!**"
        )
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        await status_msg.edit_text(
            f"❌ **Download failed**\n\n"
            f"Error: {str(e)}\n\n"
            f"Please try again."
        )


# ============== Web Server for File Serving ==============

async def handle_download(request: web.Request) -> web.StreamResponse:
    """Handle file download requests - serve from local storage."""
    file_hash = request.match_info.get("file_hash")
    
    if file_hash not in file_cache:
        return web.Response(text="File not found or link expired", status=404)
    
    file_info = file_cache[file_hash]
    local_path = Path(file_info.get("local_path", ""))
    
    if not local_path.exists():
        return web.Response(text="File not found on server", status=404)
    
    file_name = file_info["file_name"]
    file_size = file_info["file_size"]
    mime_type = file_info["mime_type"]
    
    # Parse Range header for resume support
    range_header = request.headers.get("Range", "")
    start = 0
    end = file_size - 1
    
    if range_header and range_header.startswith("bytes="):
        range_spec = range_header[6:]
        if "-" in range_spec:
            parts = range_spec.split("-")
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if parts[1] else file_size - 1
    
    content_length = end - start + 1
    is_partial = bool(range_header)
    status = 206 if is_partial else 200
    
    headers = {
        "Content-Type": mime_type,
        "Content-Disposition": f'attachment; filename="{file_name}"',
        "Content-Length": str(content_length),
        "Accept-Ranges": "bytes",
    }
    
    if is_partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    
    response = web.StreamResponse(status=status, headers=headers)
    await response.prepare(request)
    
    # Stream from local file (FAST!)
    try:
        with open(local_path, "rb") as f:
            f.seek(start)
            remaining = content_length
            chunk_size = 1024 * 1024  # 1MB chunks
            
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                chunk = f.read(read_size)
                if not chunk:
                    break
                await response.write(chunk)
                remaining -= len(chunk)
                
    except Exception as e:
        logger.error(f"File serving error: {e}")
    
    return response


async def handle_health(request: web.Request) -> web.Response:
    """Health check endpoint."""
    return web.Response(text="OK")


def run_web_server():
    """Run the web server in a separate thread."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    async def start_server():
        web_app = web.Application(client_max_size=1024**3)  # 1GB max
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
    
    print("🚀 Starting File-to-Link Bot (Server Download Mode)...")
    logger.info("Initializing bot...")
    
    # Create bot client with optimized settings
    app = Client(
        name="file_to_link_bot",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        bot_token=config.BOT_TOKEN,
        in_memory=True,
        workers=16,
        max_concurrent_transmissions=8,
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
