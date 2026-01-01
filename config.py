"""Configuration management for the File-to-Link Telegram Bot."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Bot configuration loaded from environment variables."""
    
    # Telegram credentials
    BOT_TOKEN: str
    API_ID: int
    API_HASH: str
    
    # Server URL for generating download links
    BASE_URL: str
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables."""
        required_vars = [
            "BOT_TOKEN",
            "API_ID", 
            "API_HASH",
        ]
        
        missing = [var for var in required_vars if not os.getenv(var)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        
        # Default to localhost for local development
        base_url = os.getenv("BASE_URL", "http://localhost:8080")
        
        return cls(
            BOT_TOKEN=os.getenv("BOT_TOKEN"),
            API_ID=int(os.getenv("API_ID")),
            API_HASH=os.getenv("API_HASH"),
            BASE_URL=base_url,
        )


# Global config instance
config = Config.from_env()
