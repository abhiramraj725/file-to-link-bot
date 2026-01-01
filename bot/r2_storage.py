"""Cloudflare R2 storage integration for file uploads and signed URL generation."""

import os
import uuid
from datetime import datetime
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig


class R2Storage:
    """Cloudflare R2 storage client for uploading files and generating signed URLs."""
    
    def __init__(
        self,
        account_id: str,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        link_expiry_seconds: int = 604800,  # 7 days
    ):
        self.bucket_name = bucket_name
        self.link_expiry_seconds = link_expiry_seconds
        self.endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        
        # Initialize S3 client (R2 is S3-compatible)
        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=BotoConfig(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "adaptive"},
            ),
        )
    
    def generate_unique_filename(self, original_filename: str) -> str:
        """Generate a unique filename to prevent collisions."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        
        # Get file extension
        _, ext = os.path.splitext(original_filename)
        
        # Sanitize original filename (remove special chars)
        safe_name = "".join(c for c in original_filename if c.isalnum() or c in "._-")
        safe_name = safe_name[:50]  # Limit length
        
        return f"{timestamp}_{unique_id}_{safe_name}"
    
    def upload_file(
        self,
        file_path: str,
        original_filename: str,
        content_type: str = "application/octet-stream",
        progress_callback=None,
    ) -> str:
        """
        Upload a file to R2 storage.
        
        Args:
            file_path: Path to the local file to upload
            original_filename: Original filename for generating unique key
            content_type: MIME type of the file
            progress_callback: Optional callback for progress updates
            
        Returns:
            The object key (filename) in R2
        """
        object_key = self.generate_unique_filename(original_filename)
        file_size = os.path.getsize(file_path)
        
        # Upload with progress tracking
        with open(file_path, "rb") as f:
            self.client.upload_fileobj(
                f,
                self.bucket_name,
                object_key,
                ExtraArgs={"ContentType": content_type},
                Callback=progress_callback,
            )
        
        return object_key
    
    def upload_fileobj(
        self,
        file_obj: BinaryIO,
        original_filename: str,
        content_type: str = "application/octet-stream",
        progress_callback=None,
    ) -> str:
        """
        Upload a file object to R2 storage.
        
        Args:
            file_obj: File-like object to upload
            original_filename: Original filename for generating unique key
            content_type: MIME type of the file
            progress_callback: Optional callback for progress updates
            
        Returns:
            The object key (filename) in R2
        """
        object_key = self.generate_unique_filename(original_filename)
        
        self.client.upload_fileobj(
            file_obj,
            self.bucket_name,
            object_key,
            ExtraArgs={"ContentType": content_type},
            Callback=progress_callback,
        )
        
        return object_key
    
    def generate_signed_url(self, object_key: str) -> str:
        """
        Generate a presigned URL for downloading a file.
        
        Args:
            object_key: The object key in R2
            
        Returns:
            Presigned URL valid for the configured expiry time
        """
        url = self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
            },
            ExpiresIn=self.link_expiry_seconds,
        )
        return url
    
    def delete_file(self, object_key: str) -> bool:
        """
        Delete a file from R2 storage.
        
        Args:
            object_key: The object key to delete
            
        Returns:
            True if deletion was successful
        """
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except Exception:
            return False
    
    def get_file_size(self, object_key: str) -> int:
        """Get the size of a file in R2."""
        response = self.client.head_object(Bucket=self.bucket_name, Key=object_key)
        return response["ContentLength"]
