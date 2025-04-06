from fastapi import FastAPI, Depends, Request, HTTPException, Security
from src.agent import get_workflow
from langgraph.checkpoint.memory import MemorySaver
from pydantic import BaseModel
from utility.logging_config import get_logger, LoggingMiddleware
from settings import get_settings
import time
import contextlib
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader, APIKey
import secrets
import os

# Initialize logger
logger = get_logger("http_server")

# Initialize workflow
checkpointer = MemorySaver()
agent_workflow = get_workflow()
agent_graph = agent_workflow.compile(checkpointer=checkpointer)

# Initialize FastAPI app
app = FastAPI(
    title="Indonesia Supreme Court LLM Agent",
    description="API for the Indonesia Supreme Court LLM Agent",
    version="1.0.0",
    docs_url=None if os.getenv("ENVIRONMENT") == "production" else "/docs",
    redoc_url=None if os.getenv("ENVIRONMENT") == "production" else "/redoc",
)

# Security settings
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    max_age=86400,
)

# Add logging middleware
app.add_middleware(LoggingMiddleware)

# Add request ID middleware
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # Get request ID from scope
        request_id = request.scope.get("request_id", "-")
        # Make it available in the request state
        request.state.request_id = request_id
        response = await call_next(request)
        return response

app.add_middleware(RequestIDMiddleware)

class ChatbotResponse(BaseModel):
    response: str
    references: list[str]

async def verify_api_key(api_key: APIKey = Security(api_key_header)):
    settings = get_settings()
    if not settings.api_key:
        # If no API key is configured, don't validate
        return True

    if api_key != settings.api_key:
        logger.warning("Invalid API key attempt", extra={"ip": "REDACTED"})
        raise HTTPException(
            status_code=403,
            detail="Invalid API key"
        )
    return True

@contextlib.contextmanager
def log_timing(name, extra=None):
    """Context manager to log execution time of a block of code."""
    if extra is None:
        extra = {}

    start_time = time.time()
    try:
        yield
    finally:
        duration = int((time.time() - start_time) * 1000)
        extra["duration"] = duration
        logger.info(f"{name} completed in {duration}ms", extra=extra)


@app.post("/chatbot/user_message", response_model=ChatbotResponse)
async def send_message(thread_id: str, user_message: str, request: Request, api_key_valid: bool = Depends(verify_api_key)) -> ChatbotResponse:
    # Get request ID from request state
    request_id = request.state.request_id
    logging_context = {"request_id": request_id}

    logger.info(
        f"Received message for thread {thread_id}: {user_message[:50]}{'...' if len(user_message) > 50 else ''}",
        extra=logging_context
    )

    references = []

    user_input = {
        "messages": [("user", user_message)],
    }

    graph_run_config = {
        "configurable": {
            # langgraph standard for session/thread id
            "thread_id": thread_id,
        },
    }

    with log_timing("Agent processing", extra=logging_context):
        agent_graph_state = await agent_graph.ainvoke(user_input, graph_run_config)

    ai_response = agent_graph_state["messages"][-1]
    response = str(ai_response.content)

    if "references" in ai_response.additional_kwargs:
        references = ai_response.additional_kwargs["references"]
        logger.info(f"References found: {len(references)}", extra=logging_context)

    return ChatbotResponse(response=response, references=references)


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


# Log application startup
@app.on_event("startup")
async def startup_event():
    settings = get_settings()
    env = os.getenv("ENVIRONMENT", "development")
    logger.info(f"Starting application on port {settings.port} with log level {settings.log_level} in {env} environment")

    # Generate API key if needed
    if not hasattr(settings, 'api_key') or not settings.api_key:
        logger.warning("No API key configured - API is open without authentication")


# Log application shutdown
@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutting down")
