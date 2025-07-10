"""
Configuration management for the Document RAG System.
Centralized configuration with environment variable support for sensitive data only.
All other settings are loaded from config.json.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def load_system_config() -> Dict[str, Any]:
    """Load system configuration from config.json"""
    config_path = Path(__file__).parent / "config.json"
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config.get("system", {})

class Settings(BaseSettings):
    """
    Application settings with environment variable support for sensitive data only.
    All other configuration is loaded from config.json.
    """
    
    # Only sensitive data from environment variables
    google_api_key: Optional[str] = Field(default=None, env="GOOGLE_API_KEY")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow extra attributes
        extra = "allow"
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Load system configuration from config.json
        system_config = load_system_config()
        
        # Set all system settings from config as attributes
        for key, value in system_config.items():
            if key in ["documents_path", "chroma_db_path"]:
                setattr(self, key, Path(value))
            else:
                setattr(self, key, value)

# Global settings instance
settings = Settings()

def ensure_directories():
    """Ensure all required directories exist."""
    settings.documents_path.mkdir(exist_ok=True)
    settings.chroma_db_path.mkdir(exist_ok=True)

def validate_settings() -> bool:
    """Validate that all required settings are properly configured."""
    # Check LLM provider and API key
    if settings.llm_provider == "google":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when using Google/Gemini models")
    
    # Check embedding provider and API key
    if settings.embedding_provider == "google":
        if not settings.google_api_key:
            raise ValueError("GOOGLE_API_KEY is required when using Google embeddings")
    
    return True

# Initialize on import
ensure_directories()

if __name__ == "__main__":
    # Test configuration
    try:
        validate_settings()
        print("✅ Configuration valid")
        print(f"Documents path: {settings.documents_path}")
        print(f"ChromaDB path: {settings.chroma_db_path}")
        print(f"Embedding model: {settings.embedding_model} ({settings.embedding_provider})")
        print(f"LLM model: {settings.llm_model} ({settings.llm_provider})")
        
        # Show model capabilities
        model_config = get_model_config(settings.llm_provider, settings.llm_model)
        if model_config:
            print(f"Max tokens: {model_config.get('max_tokens', 'unknown')}")
            print(f"Cost per 1K tokens: ${model_config.get('cost_per_1k_tokens', 'unknown')}")
            
    except Exception as e:
        print(f"❌ Configuration error: {e}") 