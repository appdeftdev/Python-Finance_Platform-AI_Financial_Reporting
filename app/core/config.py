from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import AnyHttpUrl, field_validator
import os
import dotenv
import logging

logger = logging.getLogger(__name__)

try:
    dotenv.load_dotenv()
    print("Loaded .env file")
except Exception as e:
    logger.warning(f"Could not load .env file: {e}")

class Settings(BaseSettings):
    # API Configuration
    API_V1_STR: str = os.getenv("API_V1_STR", "/api/v1")
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Pratima AI Business")
    VERSION: str = os.getenv("VERSION", "1.0.0")
    DESCRIPTION: str = os.getenv("DESCRIPTION", "AI Business Platform")
    
    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    ACCESS_TOKEN_EXPIRE_MINUTES: Optional[int] = None
    
    #SMTP
    SMTP_SERVER: str = os.getenv("SMTP_SERVER","")
    SMTP_PORT: int = os.getenv("SMTP_PORT",465)
    EMAIL_ADDRESS: str = os.getenv("EMAIL_ADDRESS","")
    EMAIL_PASSWORD: str = os.getenv("EMAIL_PASSWORD","")
    
    
    @field_validator('ACCESS_TOKEN_EXPIRE_DAYS', mode='before')
    @classmethod
    def validate_access_token_expire_days(cls, v):
        if v is None:
            return 7
        try:
            return int(v)
        except (ValueError, TypeError):
            return 7
    
    @field_validator('ACCESS_TOKEN_EXPIRE_MINUTES', mode='before')
    @classmethod
    def validate_access_token_expire_minutes(cls, v):
        if v is None:
            env_value = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
            try:
                return int(env_value)
            except (ValueError, TypeError):
                return 30
        try:
            return int(v)
        except (ValueError, TypeError):
            return 30
    
    # CORS
    ALLOWED_HOSTS: str = os.getenv("ALLOWED_HOSTS", "*")
    
    @field_validator('ALLOWED_HOSTS', mode='after')
    @classmethod
    def validate_allowed_hosts(cls, v):
        if isinstance(v, str):
            if v == "*":
                return ["*"]
            return [host.strip() for host in v.split(",") if host.strip()]
        return v
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")
    print("DATABASE_URL", DATABASE_URL)
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "")
    
    # Environment
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = False
    
    @field_validator('DEBUG', mode='before')
    @classmethod
    def validate_debug(cls, v):
        if isinstance(v, str):
            return v.lower() in ('true', '1', 'yes', 'on')
        return bool(v)
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"
        
settings = Settings() 