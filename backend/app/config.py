"""
VARUNA AI - Application Configuration
Type-safe configuration with Pydantic Settings.
Never commits secrets or exposes private credentials to frontend.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    # App Identity
    APP_NAME: str = "VARUNA AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    
    # Server & Security
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    SECRET_KEY: str = Field(default="varuna-insecure-dev-secret-key-change-in-prod-64byteslong!", min_length=32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    
    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ]
    
    # Database
    DATABASE_URL: str = "sqlite:///./varuna.db"
    
    # AI Gateway Credentials (Optional in dev, mock provider works without external key)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    DEFAULT_AI_PROVIDER: str = "simulator"  # simulator, openai, ollama
    
    # Credit Economics
    CREDIT_VALUE_INR: float = 0.10  # 1 credit = 10 paise (INR 0.10)
    SIGNUP_FREE_CREDITS: float = 100.0  # ₹10 worth of complimentary credits
    MAX_RESERVATION_CREDITS: float = 50.0  # safety cap per single query
    
    # Razorpay (India First Payment Gateway)
    RAZORPAY_KEY_ID: str = "rzp_test_mock_key_id"
    RAZORPAY_KEY_SECRET: str = "rzp_test_mock_secret_key"
    RAZORPAY_WEBHOOK_SECRET: str = "rzp_webhook_secret_key_prod"
    
    # File Storage
    UPLOAD_DIR: str = "./storage/uploads"
    MAX_FILE_SIZE_BYTES: int = 15 * 1024 * 1024  # 15 MB
    ALLOWED_EXTENSIONS: List[str] = [".pdf", ".csv", ".xlsx", ".txt", ".png", ".jpg", ".jpeg"]
    
    # Cost & Emergency Controls
    GLOBAL_AI_KILL_SWITCH: bool = False
    DAILY_ORG_SPENDING_CAP_CREDITS: float = 5000.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
