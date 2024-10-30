from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

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


@app.get("/health")
async def health_check():
    """
    Check if the API is running.

    Returns:
    - **message**: Status message indicating the API is operational
    """
    return {"message": "Ok!"}


@app.get("/api-schema")
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
