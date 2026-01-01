"""Message handlers for the File-to-Link Telegram Bot (Gofile version)."""

import os
import tempfile
from datetime import datetime

from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.handlers import MessageHandler

from .gofile_storage import GofileStorage


class BotHandlers:
    """Handles all bot message interactions."""
    
    def __init__(self, app: Client):
        self.app = app
        self.storage = GofileStorage()
        self._register_handlers()
    
    def _register_handlers(self):
        """Register all message handlers."""
        # /start command
        self.app.add_handler(MessageHandler(self.start_command, filters.command("start")))
        
        # /help command
        self.app.add_handler(MessageHandler(self.help_command, filters.command("help")))
        
        # File handler (documents, videos, audio, photos)
        self.app.add_handler(MessageHandler(
            self.handle_file,
            filters.document | filters.video | filters.audio | filters.voice | filters.video_note
        ))
        
        # Photo handler (compressed images)
        self.app.add_handler(MessageHandler(self.handle_photo, filters.photo))
    
    async def start_command(self, client: Client, message: Message):
        """Handle /start command."""
        welcome_text = """
🔗 **Welcome to File-to-Link Bot!**

I convert your files into downloadable links.

**How to use:**
1. Send me any file (up to 4GB with Telegram Premium)
2. Wait for upload to complete
3. Get your download link!

**Supported files:**
📄 Documents (PDF, ZIP, etc.)
🎬 Videos
🎵 Audio files
🖼️ Photos

Send /help for more information.
        """
        await message.reply_text(welcome_text.strip())
    
    async def help_command(self, client: Client, message: Message):
        """Handle /help command."""
        help_text = """
📖 **Help & Information**

**Commands:**
• /start - Start the bot
• /help - Show this help message

**File Limits:**
• Maximum file size: 4GB (requires Telegram Premium)
• Free users: 2GB max

**Tips:**
• Large files may take a few minutes to process
• Keep the chat open during upload for progress updates
• Download links work in any browser

**Storage:**
• Files are hosted on Gofile.io (free service)
• Links remain active as long as files are downloaded occasionally
        """
        await message.reply_text(help_text.strip())
    
    async def handle_file(self, client: Client, message: Message):
        """Handle incoming files (documents, videos, audio)."""
        # Determine file info based on message type
        if message.document:
            file = message.document
            file_name = file.file_name or f"document_{file.file_id[:8]}"
            file_size = file.file_size
        elif message.video:
            file = message.video
            file_name = file.file_name or f"video_{file.file_id[:8]}.mp4"
            file_size = file.file_size
        elif message.audio:
            file = message.audio
            file_name = file.file_name or f"audio_{file.file_id[:8]}.mp3"
            file_size = file.file_size
        elif message.voice:
            file = message.voice
            file_name = f"voice_{file.file_id[:8]}.ogg"
            file_size = file.file_size
        elif message.video_note:
            file = message.video_note
            file_name = f"video_note_{file.file_id[:8]}.mp4"
            file_size = file.file_size
        else:
            return
        
        await self._process_file(message, file, file_name, file_size)
    
    async def handle_photo(self, client: Client, message: Message):
        """Handle incoming photos."""
        # Get the highest resolution photo
        photo = message.photo
        file_name = f"photo_{photo.file_id[:8]}.jpg"
        file_size = photo.file_size
        
        await self._process_file(message, photo, file_name, file_size)
    
    async def _process_file(
        self,
        message: Message,
        file,
        file_name: str,
        file_size: int,
    ):
        """Process and upload a file, then return the download link."""
        # Format file size for display
        size_str = self._format_size(file_size)
        
        # Send initial processing message
        status_msg = await message.reply_text(
            f"📥 **Downloading from Telegram...**\n"
            f"📄 File: `{file_name}`\n"
            f"📊 Size: {size_str}\n\n"
            f"Please wait..."
        )
        
        temp_path = None
        try:
            # Create temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
                temp_path = temp_file.name
            
            # Download file from Telegram with progress
            last_update_time = [datetime.now()]
            
            async def download_progress(current, total):
                now = datetime.now()
                # Update every 2 seconds to avoid rate limits
                if (now - last_update_time[0]).seconds >= 2:
                    last_update_time[0] = now
                    percent = (current / total) * 100
                    progress_bar = self._create_progress_bar(percent)
                    try:
                        await status_msg.edit_text(
                            f"📥 **Downloading from Telegram...**\n"
                            f"📄 File: `{file_name}`\n"
                            f"📊 Size: {size_str}\n\n"
                            f"{progress_bar} {percent:.1f}%"
                        )
                    except Exception:
                        pass  # Ignore edit errors
            
            await message.download(file_name=temp_path, progress=download_progress)
            
            # Update status for upload
            await status_msg.edit_text(
                f"📤 **Uploading to Gofile...**\n"
                f"📄 File: `{file_name}`\n"
                f"📊 Size: {size_str}\n\n"
                f"This may take a moment for large files..."
            )
            
            # Upload to Gofile
            download_url, _ = await self.storage.upload_file(temp_path)
            
            # Send success message with download link
            await status_msg.edit_text(
                f"✅ **Upload Complete!**\n\n"
                f"📄 **File:** `{file_name}`\n"
                f"📊 **Size:** {size_str}\n\n"
                f"🔗 **Download Link:**\n{download_url}\n\n"
                f"💡 Link stays active as long as the file is downloaded occasionally."
            )
            
        except Exception as e:
            error_msg = str(e)
            if "too large" in error_msg.lower():
                error_msg = "File is too large for Gofile. Try a smaller file."
            
            await status_msg.edit_text(
                f"❌ **Upload Failed**\n\n"
                f"Error: {error_msg}\n\n"
                f"Please try again."
            )
        finally:
            # Clean up temp file
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    def _format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.2f} TB"
    
    def _create_progress_bar(self, percent: float, length: int = 20) -> str:
        """Create a text-based progress bar."""
        filled = int(length * percent / 100)
        empty = length - filled
        return f"[{'█' * filled}{'░' * empty}]"
