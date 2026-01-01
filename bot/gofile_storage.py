"""Gofile.io storage integration - completely free, no account required."""

import os
import aiohttp
import aiofiles
from typing import Optional, Tuple


class GofileStorage:
    """Gofile.io client for uploading files and getting download links."""
    
    BASE_URL = "https://api.gofile.io"
    
    def __init__(self):
        self._server: Optional[str] = None
    
    async def _get_best_server(self) -> str:
        """Get the best available server for upload."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.BASE_URL}/servers") as resp:
                data = await resp.json()
                if data["status"] == "ok":
                    # Get the first available server
                    servers = data["data"]["servers"]
                    if servers:
                        return servers[0]["name"]
        raise Exception("No Gofile servers available")
    
    async def upload_file(
        self,
        file_path: str,
        progress_callback=None,
    ) -> Tuple[str, str]:
        """
        Upload a file to Gofile.
        
        Args:
            file_path: Path to the local file to upload
            progress_callback: Optional async callback for progress updates (current, total)
            
        Returns:
            Tuple of (download_page_url, direct_download_url)
        """
        # Get best server
        server = await self._get_best_server()
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"
        
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Create form data with file
        async with aiohttp.ClientSession() as session:
            # Read file and upload
            data = aiohttp.FormData()
            
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
                data.add_field(
                    'file',
                    file_content,
                    filename=file_name,
                    content_type='application/octet-stream'
                )
            
            async with session.post(upload_url, data=data) as resp:
                result = await resp.json()
                
                if result["status"] == "ok":
                    file_data = result["data"]
                    download_page = file_data["downloadPage"]
                    
                    # Note: Direct download requires the file ID
                    # The download page is what users will use
                    return download_page, download_page
                else:
                    raise Exception(f"Upload failed: {result.get('message', 'Unknown error')}")
    
    async def upload_file_chunked(
        self,
        file_path: str,
        chunk_size: int = 1024 * 1024,  # 1MB chunks
        progress_callback=None,
    ) -> Tuple[str, str]:
        """
        Upload a large file to Gofile with progress tracking.
        
        Args:
            file_path: Path to the local file to upload
            chunk_size: Size of chunks for progress tracking
            progress_callback: Optional async callback for progress (current, total)
            
        Returns:
            Tuple of (download_page_url, direct_download_url)
        """
        server = await self._get_best_server()
        upload_url = f"https://{server}.gofile.io/contents/uploadfile"
        
        file_size = os.path.getsize(file_path)
        file_name = os.path.basename(file_path)
        
        # Use streaming upload for large files
        async with aiohttp.ClientSession() as session:
            # Create a file reader that tracks progress
            async def file_reader():
                uploaded = 0
                async with aiofiles.open(file_path, 'rb') as f:
                    while True:
                        chunk = await f.read(chunk_size)
                        if not chunk:
                            break
                        uploaded += len(chunk)
                        if progress_callback:
                            await progress_callback(uploaded, file_size)
                        yield chunk
            
            # For very large files, we need to read into memory
            # Gofile doesn't support chunked transfer encoding
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            data = aiohttp.FormData()
            data.add_field(
                'file',
                file_content,
                filename=file_name,
                content_type='application/octet-stream'
            )
            
            async with session.post(upload_url, data=data) as resp:
                result = await resp.json()
                
                if result["status"] == "ok":
                    file_data = result["data"]
                    download_page = file_data["downloadPage"]
                    return download_page, download_page
                else:
                    raise Exception(f"Upload failed: {result.get('message', 'Unknown error')}")


# Alternative: PixelDrain (backup option)
class PixelDrainStorage:
    """PixelDrain.com client - another free option."""
    
    UPLOAD_URL = "https://pixeldrain.com/api/file"
    
    async def upload_file(self, file_path: str) -> str:
        """Upload file and return download URL."""
        file_name = os.path.basename(file_path)
        
        async with aiohttp.ClientSession() as session:
            async with aiofiles.open(file_path, 'rb') as f:
                file_content = await f.read()
            
            data = aiohttp.FormData()
            data.add_field(
                'file',
                file_content,
                filename=file_name
            )
            
            async with session.post(self.UPLOAD_URL, data=data) as resp:
                if resp.status == 201:
                    result = await resp.json()
                    file_id = result["id"]
                    return f"https://pixeldrain.com/u/{file_id}"
                else:
                    raise Exception(f"Upload failed with status {resp.status}")
