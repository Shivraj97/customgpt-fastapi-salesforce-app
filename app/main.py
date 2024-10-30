from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
import redis
from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import secrets
from datetime import datetime
import json

# Database setup
SQLALCHEMY_DATABASE_URL = "postgresql://myuser:mypassword@localhost/mydb"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, bind=engine)
Base = declarative_base()

# Redis setup
redis_client = redis.Redis(host='localhost', port=6379, db=0)

# Database model


class APIKey(Base):
    __tablename__ = "api_keys"

    api_key = Column(String, primary_key=True, index=True)
    email = Column(String, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# Create tables
Base.metadata.create_all(bind=engine)

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
    api_key: str

    class Config:
        json_schema_extra = {
            "example": {
                "numbers": [5, 3],
                "api_key": "your_api_key_here"
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
    title="Greeting App",
    description="Given a name it will greet you",
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
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)


@app.post("/")
async def greeting(request: GreetingRequest):
    """
    Send a greeting message to a person.

    Parameters:
    - **request**: A GreetingRequest object containing a name

    Returns:
    - **message**: A greeting message with the provided name
    """
    return {"message": f"Hello {request.name} 👋"}


@app.post("/generate-key", tags=["API Keys"])
async def generate_api_key(request: EmailRequest, db: Session = Depends(get_db)):
    """
    Generate and store an API key for the provided email.

    Parameters:
    - request: EmailRequest with email address
    Returns:
    - api_key: The newly generated API key
    """
    api_key = secrets.token_urlsafe(32)
    db_api_key = APIKey(api_key=api_key, email=request.email)
    db.add(db_api_key)
    db.commit()
    return {"api_key": api_key}


@app.post("/sum", tags=["Operations"])
async def sum_numbers(
    request: SumRequest,
    db: Session = Depends(get_db)
):
    """
    Sum a list of numbers with API key authentication and rate limiting.

    Requires valid API key. Limited to 5 requests per minute per key.
    Returns the sum of provided numbers.

    Parameters:
    - request: Numbers to sum and API key
    Returns:
    - result: Sum of numbers
    """
    # Verify API key
    db_api_key = db.query(APIKey).filter(
        APIKey.api_key == request.api_key).first()
    if not db_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    # Check rate limit
    check_rate_limit(request.api_key)

    return {"result": sum(request.numbers)}


@app.post("/subtract", tags=["Operations"])
async def subtract_numbers(
    request: SumRequest,
    db: Session = Depends(get_db)
):
    """
    Subtract numbers sequentially with API key authentication and rate limiting.

    Requires valid API key. Limited to 5 requests per minute per key.
    Subtracts numbers sequentially from the first number.

    Parameters:
    - request: Numbers to subtract and API key
    Returns:
    - result: Final subtraction result
    """
    # Verify API key
    db_api_key = db.query(APIKey).filter(
        APIKey.api_key == request.api_key).first()
    if not db_api_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    # Check rate limit
    check_rate_limit(request.api_key)

    # Subtract numbers sequentially starting from the first number
    if not request.numbers:
        return {"result": 0}
    result = request.numbers[0]
    for num in request.numbers[1:]:
        result -= num

    return {"result": result}


@app.get("/health")
async def health_check():
    """
    Check if the API is running.

    Returns:
    - **message**: Status message indicating the API is operational
    """
    return {"message": "Ok!"}


# @app.get("/api-schema")
# async def get_openapi_schema():
#     """
#     Get the OpenAPI schema for this API.

#     Returns:
#     - OpenAPI JSON schema
#     """
#     return app.openapi()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
