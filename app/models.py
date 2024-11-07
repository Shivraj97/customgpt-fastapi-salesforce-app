from sqlalchemy import Column, String, DateTime
from datetime import datetime
from .database import Base


class OAuthState(Base):
    __tablename__ = "oauth_states"

    state = Column(String, primary_key=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class SalesforceToken(Base):
    __tablename__ = "salesforce_tokens"

    access_token = Column(String, primary_key=True)
    refresh_token = Column(String)
    instance_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class APIKey(Base):
    __tablename__ = "api_keys"

    api_key = Column(String, primary_key=True, index=True)
    email = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
