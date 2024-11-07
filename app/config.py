import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SALESFORCE_CLIENT_ID: str = os.getenv("SALESFORCE_CLIENT_ID")
    SALESFORCE_CLIENT_SECRET: str = os.getenv("SALESFORCE_CLIENT_SECRET")
    # Update this to match your domain
    SALESFORCE_REDIRECT_URI: str = os.getenv("SALESFORCE_REDIRECT_URI")
    CHATGPT_REDIRECT_URI: str = os.getenv("CHATGPT_REDIRECT_URI")
    SALESFORCE_AUTH_URL: str = "https://login.salesforce.com/services/oauth2/authorize"
    SALESFORCE_TOKEN_URL: str = "https://login.salesforce.com/services/oauth2/token"

    class Config:
        env_file = ".env"


settings = Settings()
