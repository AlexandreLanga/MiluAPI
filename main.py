import asyncio
from contextlib import asynccontextmanager
import logging
import os
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from redis.asyncio import Redis
from starlette.types import ASGIApp, Receive, Scope, Send

from api_documentation import DESCRIPTION, TITLE, VERSION
from services.MiluService import (
    GEMINI_TIMEOUT_MS,
    UserMessage,
    chat_assistant,
    websocket_chat,
)
from services.RateLimitMiddleware import (
    ChatRateLimitMiddleware,
    InMemoryRateLimiter,
    PayloadLimitMiddleware,
    RATE_LIMIT_REQUESTS,
    RATE_LIMIT_WINDOW_SECONDS,
    RedisRateLimiter,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
MAX_GEMINI_CONCURRENT_REQUESTS = int(
    os.getenv("MAX_GEMINI_CONCURRENT_REQUESTS", "5")
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if MAX_GEMINI_CONCURRENT_REQUESTS < 1:
        raise ValueError("MAX_GEMINI_CONCURRENT_REQUESTS must be at least 1")

    app.state.gemini_semaphore = asyncio.Semaphore(
        MAX_GEMINI_CONCURRENT_REQUESTS
    )
    redis_client = None
    redis_url = os.getenv("RATE_LIMIT_REDIS_URL")

    try:
        if redis_url:
            redis_client = Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await redis_client.ping()
            app.state.rate_limiter = RedisRateLimiter(
                redis_client,
                RATE_LIMIT_REQUESTS,
                RATE_LIMIT_WINDOW_SECONDS,
            )
        else:
            logging.warning(
                "Using process-local rate limiting; configure "
                "RATE_LIMIT_REDIS_URL before running multiple workers or replicas."
            )
            app.state.rate_limiter = InMemoryRateLimiter(
                RATE_LIMIT_REQUESTS,
                RATE_LIMIT_WINDOW_SECONDS,
            )

        api_key = os.getenv("GEMINI_API_KEY")
        if api_key:
            async with genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS),
            ).aio as gemini_client:
                app.state.gemini_client = gemini_client
                yield
        else:
            app.state.gemini_client = None
            yield
    finally:
        app.state.gemini_client = None
        if redis_client is not None:
            await redis_client.aclose()


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("path") != "/chat" or scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        started_at = perf_counter()
        status_code = 500

        async def log_response(message: dict) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, log_response)
        finally:
            logging.info(
                "api_request method=%s path=/chat status=%d duration_ms=%.2f",
                scope.get("method", "unknown"),
                status_code,
                (perf_counter() - started_at) * 1000,
            )


app = FastAPI(
    title=TITLE,
    description=DESCRIPTION,
    version=VERSION,
    lifespan=lifespan,
)

app.add_middleware(PayloadLimitMiddleware)
app.add_middleware(ChatRateLimitMiddleware)
app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://alexandrelanga.github.io"],
    allow_credentials=False,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


@app.post("/chat")
async def chat_assistant_endpoint(data: UserMessage):
    semaphore = app.state.gemini_semaphore
    try:
        await asyncio.wait_for(semaphore.acquire(), timeout=1)
    except TimeoutError as exc:
        raise HTTPException(
            status_code=503,
            detail="The service is busy. Please try again.",
            headers={"Retry-After": "1"},
        ) from exc

    try:
        return await chat_assistant(
            data.message,
            data.language,
            app.state.gemini_client,
        )
    finally:
        semaphore.release()


@app.websocket("/chat")
async def websocket_chat_route(websocket: WebSocket):
    await websocket_chat(
        websocket,
        app.state.gemini_client,
        app.state.gemini_semaphore,
    )


@app.get("/healthz", include_in_schema=False)
async def health_check():
    return {"status": "ok"}
