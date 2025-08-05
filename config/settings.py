from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # API Keys
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    spoonacular_api_key: Optional[str] = None
    
    # Server Configuration
    port: int = 3000
    debug: bool = True
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # Allow OPENAI_API_KEY or openai_api_key


# Create singleton instance
settings = Settings()