from datetime import datetime, timedelta
from typing import Annotated
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi import Form, Query, Security, Depends, HTTPException
from urllib.parse import quote
from .config import settings
from sqlalchemy.orm import Session
import requests
from fastapi import HTTPException, Depends, Header, Request
import os
from urllib.parse import urlencode
from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
import redis
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import secrets
from datetime import datetime
import json
import base64
import hashlib
import secrets
from sqlalchemy.orm import Session
from .config import settings
from app.database import SessionLocal, engine
from app.models import Base, OAuthState, APIKey, SalesforceToken


# Environment variables
CLIENT_ID = os.getenv("SALESFORCE_CLIENT_ID")
CLIENT_SECRET = os.getenv("SALESFORCE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SALESFORCE_REDIRECT_URI")
CHATGPT_REDIRECT_URI = os.getenv("CHATGPT_REDIRECT_URI")
AUTHORIZATION_BASE_URL = "https://login.salesforce.com/services/oauth2/authorize"
TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"

# Redis setup
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Create tables
Base.metadata.create_all(bind=engine)


def refresh_salesforce_token(db: Session, token: SalesforceToken) -> SalesforceToken:
    """Refresh Salesforce access token using refresh token"""
    response = requests.post(
        settings.SALESFORCE_TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "client_id": settings.SALESFORCE_CLIENT_ID,
            "client_secret": settings.SALESFORCE_CLIENT_SECRET,
            "refresh_token": token.refresh_token
        }
    )

    if response.status_code != 200:
        db.delete(token)
        db.commit()
        raise HTTPException(status_code=401, detail="Failed to refresh token")

    token_data = response.json()
    token.access_token = token_data["access_token"]
    token.created_at = datetime.utcnow()
    db.commit()

    return token


async def verify_salesforce_token(token: str, db: Session) -> bool:
    """Verify token with Salesforce and refresh if needed"""
    headers = {
        'Authorization': f'Bearer {token}'
    }
    response = requests.get(
        'https://login.salesforce.com/services/oauth2/userinfo', headers=headers)

    if response.status_code == 401:
        # Token expired, try to refresh
        db_token = db.query(SalesforceToken).filter(
            SalesforceToken.access_token == token
        ).first()

        if db_token:
            try:
                new_token = await refresh_salesforce_token(db_token, db)
                headers['Authorization'] = f'Bearer {new_token}'
                response = requests.get(
                    'https://login.salesforce.com/services/oauth2/userinfo',
                    headers=headers
                )
            except HTTPException:
                return False

    return response.status_code == 200


# Define single security scheme for the entire app
security = HTTPBearer(
    scheme_name="Salesforce OAuth2",
    description="Enter the Salesforce access token",
    auto_error=True
)


# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# New request models


class EmailRequest(BaseModel):
    email: EmailStr

    class Config:
        json_schema_extra = {
            "example": {
                "email": "user@example.com"
            }
        }


class SumRequest(BaseModel):
    numbers: list[float]

    class Config:
        json_schema_extra = {
            "example": {
                "numbers": [5, 3],
            }
        }

# Rate limiting function


def check_rate_limit(api_key: str):
    key = f"rate_limit:{api_key}"
    pipe = redis_client.pipeline()

    current_time = datetime.utcnow().timestamp()
    calls = json.loads(redis_client.get(key) or "[]")

    recent_calls = [t for t in calls if current_time - t < 60]

    if len(recent_calls) >= 2:  # 2 requests per minute
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again in a minute."
        )

    recent_calls.append(current_time)
    redis_client.set(key, json.dumps(recent_calls), ex=60)
    return True

# Define the request model


class GreetingRequest(BaseModel):
    name: str

    class Config:
        json_schema_extra = {
            "example": {
                "name": "John Doe"
            }
        }


# Customize OpenAPI documentation
app = FastAPI(
    title="Salesforce Metadata explorer app",
    description="An API for accessing Salesforce metadata.",
    version="1.0.0",
    terms_of_service="http://example.com/terms/",
    contact={
        "name": "Your Name",
        "url": "http://example.com/contact/",
        "email": "your@email.com",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    servers=[
        {"url": "https://choice-electric-cicada.ngrok-free.app",
            "description": "Production server"}
    ],
)


# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    # Allow localhost:3000 and ChatGPT
    allow_origins=["http://localhost:3000", "https://chat.openai.com"],
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


# @app.post("/")
# async def greeting(request: GreetingRequest):
#     """
#     Send a greeting message to a person.

#     Parameters:
#     - **request**: A GreetingRequest object containing a name

#     Returns:
#     - **message**: A greeting message with the provided name
#     """
#     return {"message": f"Hello {request.name} 👋"}


# @app.post("/generate-key", tags=["API Keys"])
# async def generate_api_key(request: EmailRequest, db: Session = Depends(get_db)):
#     """
#     Generate and store an API key for the provided email.

#     Parameters:
#     - request: EmailRequest with email address
#     Returns:
#     - api_key: The newly generated API key
#     """
#     # # Check if email already has an API key
#     # existing_key = db.query(APIKey).filter(
#     #     APIKey.email == request.email).first()
#     # if existing_key:
#     #     raise HTTPException(
#     #         status_code=400,
#     #         detail="An API key already exists for this email address"
#     #     )
#     api_key = secrets.token_urlsafe(32)
#     db_api_key = APIKey(api_key=api_key, email=request.email)
#     db.add(db_api_key)
#     db.commit()
#     return {"api_key": api_key}


# @app.post("/sum", tags=["Operations"])
# async def sum_numbers(
#     request: SumRequest,
#     credentials: HTTPAuthorizationCredentials = Security(security),
#     db: Session = Depends(get_db)
# ):
#     """
#     Sum a list of numbers with Salesforce OAuth authentication and rate limiting.
#     """
#     # Verify token
#     if not await verify_salesforce_token(credentials.credentials, db):
#         raise HTTPException(
#             status_code=401,
#             detail="Invalid or expired token"
#         )

#     # Check rate limit
#     check_rate_limit(credentials.credentials)

#     return {"result": sum(request.numbers)}


# @app.post("/subtract", tags=["Operations"])
# async def subtract_numbers(
#     request: SumRequest,
#     credentials: HTTPAuthorizationCredentials = Security(security),
#     db: Session = Depends(get_db)
# ):
#     """
#     Subtract numbers sequentially with Salesforce OAuth authentication and rate limiting.
#     """
#     # Verify token
#     if not await verify_salesforce_token(credentials.credentials, db):
#         raise HTTPException(
#             status_code=401,
#             detail="Invalid or expired token"
#         )

#     # Check rate limit
#     check_rate_limit(credentials.credentials)

#     if not request.numbers:
#         return {"result": 0}
#     result = request.numbers[0]
#     for num in request.numbers[1:]:
#         result -= num

#     return {"result": result}


@app.get("/health")
async def health_check():
    """
    Check if the API is running.

    Returns:
    - **message**: Status message indicating the API is operational
    """
    return {"message": "Ok!"}


@app.get("/login")
async def login(state, db: Session = Depends(get_db)):
    """Initiate Salesforce OAuth flow"""
    print("LOGIN API CALLED")
    print(f"REDIRECT URI: {REDIRECT_URI}")  # Add this line
    # state = secrets.token_urlsafe(32)

    # Store state in database
    db_state = OAuthState(state=state)
    db.add(db_state)
    db.commit()

    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": CHATGPT_REDIRECT_URI,
        "state": state,
    }

    authorization_url = f"{AUTHORIZATION_BASE_URL}?{urlencode(params)}"
    return RedirectResponse(authorization_url)
# Single security scheme for protected routes
oauth2_scheme = HTTPBearer()

# Public routes (no auth required)


@app.post("/callback")
async def callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """Handle OAuth callback from Salesforce"""
    # Get form data from request body
    form_data = await request.form()
    print("form_data", form_data)

    # Extract code and state from form data
    code = form_data.get("code")
    # state = form_data.get("state")

    # if not code or not state:
    #     raise HTTPException(
    #         status_code=400,
    #         detail="Missing required parameters"
    #     )

    # # Verify state
    # db_state = db.query(OAuthState).filter(OAuthState.state == state).first()
    # if not db_state:
    #     raise HTTPException(
    #         status_code=400,
    #         detail="Invalid state parameter"
    #     )

    # Exchange code for token
    token_response = requests.post(
        settings.SALESFORCE_TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": settings.SALESFORCE_CLIENT_ID,
            "client_secret": settings.SALESFORCE_CLIENT_SECRET,
            "redirect_uri": settings.CHATGPT_REDIRECT_URI,
            "code": code
        }
    )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail="Failed to get access token"
        )

    token_data = token_response.json()

    # Store token
    db_token = SalesforceToken(
        access_token=token_data["access_token"],
        refresh_token=token_data.get("refresh_token", ""),
        instance_url=token_data["instance_url"]
    )

    db.add(db_token)
    # db.delete(db_state)
    db.commit()
    return token_data
# Helper function to validate token and get Salesforce session


async def get_salesforce_session(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db)
) -> SalesforceToken:
    token = db.query(SalesforceToken).filter(
        SalesforceToken.access_token == credentials.credentials
    ).first()

    if not token:
        raise HTTPException(status_code=401, detail="Invalid access token")

    if datetime.utcnow() - token.created_at > timedelta(hours=2):
        token = refresh_salesforce_token(db, token)

    return token


@app.get("/metadata")
async def get_salesforce_metadata(
    token: SalesforceToken = Depends(get_salesforce_session)
):
    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "Content-Type": "application/json"
    }

    response = requests.get(
        f"{token.instance_url}/services/data/v59.0/sobjects/opportunity/describe",
        headers=headers
    )

    if response.status_code == 401:
        token = refresh_salesforce_token(db, token)
        headers["Authorization"] = f"Bearer {token.access_token}"
        response = requests.get(
            f"{token.instance_url}/services/data/v59.0/sobjects/account/describe",
            headers=headers
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch metadata after token refresh"
            )
    print(response.json())
    return {
        "metadata": "jbcwjkw"
    }

@app.get("/accounts/{account_id}")
async def get_account(
    account_id: str,
    token: SalesforceToken = Depends(get_salesforce_session)
):
    """
    Get detailed information about a specific Salesforce account
    
    Parameters:
    - account_id: The Salesforce ID of the account
    
    Returns:
    - Account details from Salesforce
    """
    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "Content-Type": "application/json"
    }

    response = requests.get(
        f"{token.instance_url}/services/data/v59.0/sobjects/Account/{account_id}",
        headers=headers
    )

    if response.status_code == 401:
        token = refresh_salesforce_token(db, token)
        headers["Authorization"] = f"Bearer {token.access_token}"
        response = requests.get(
            f"{token.instance_url}/services/data/v59.0/sobjects/Account/{account_id}",
            headers=headers
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail="Failed to fetch account details after token refresh"
            )
    
    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="Account not found"
        )

    return response.json()

# @app.get("/opportunities")
# async def get_opportunities(
#     token: SalesforceToken = Depends(get_salesforce_session)
# ):
#     query = "SELECT Id, Name, Amount, StageName, CloseDate FROM Opportunity"
#     encoded_query = quote(query)

#     headers = {
#         "Authorization": f"Bearer {token.access_token}",
#         "Content-Type": "application/json"
#     }

#     response = requests.get(
#         f"{token.instance_url}/services/data/v59.0/query/?q={encoded_query}",
#         headers=headers
#     )

#     if response.status_code == 401:
#         token = refresh_salesforce_token(db, token)
#         headers["Authorization"] = f"Bearer {token.access_token}"
#         response = requests.get(
#             f"{token.instance_url}/services/data/v59.0/query/?q={encoded_query}",
#             headers=headers
#         )

#         if response.status_code != 200:
#             raise HTTPException(
#                 status_code=response.status_code,
#                 detail="Failed to fetch opportunities after token refresh"
#             )

#     return response.json()  # @app.get("/api-schema")


async def get_openapi_schema():
    """
    Get the OpenAPI schema for this API.

    Returns:
    - OpenAPI JSON schema
    """
    return app.openapi()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
