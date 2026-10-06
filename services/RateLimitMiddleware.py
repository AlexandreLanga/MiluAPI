from collections import deque
from hashlib import sha256
import json
import logging
from math import ceil
from threading import Lock
from time import monotonic
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
CHAT_PATH = "/chat"
MAX_CHAT_BODY_BYTES = 16 * 1024

_REDIS_RATE_LIMIT_SCRIPT = """
local time = redis.call('TIME')
local now = (tonumber(time[1]) * 1000) + math.floor(tonumber(time[2]) / 1000)
local window = tonumber(ARGV[1])
local cutoff = now - window
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)
local count = redis.call('ZCARD', KEYS[1])

if count >= tonumber(ARGV[2]) then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    return math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
end

redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window + 1000)
return 0
"""


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self._limit = limit
        self._window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._checks = 0

    async def retry_after(self, client_id: str) -> int | None:
        now = monotonic()
        cutoff = now - self._window_seconds

        with self._lock:
            requests = self._requests.setdefault(client_id, deque())
            while requests and requests[0] <= cutoff:
                requests.popleft()

            if len(requests) >= self._limit:
                return max(1, ceil(requests[0] + self._window_seconds - now))

            requests.append(now)
            self._checks += 1

            if self._checks % 256 == 0:
                expired = [
                    key
                    for key, timestamps in self._requests.items()
                    if not timestamps or timestamps[-1] <= cutoff
                ]
                for key in expired:
                    del self._requests[key]

        return None


class RedisRateLimiter:
    def __init__(
        self,
        client: Redis,
        limit: int,
        window_seconds: int,
    ):
        self._client = client
        self._limit = limit
        self._window_milliseconds = window_seconds * 1000

    async def retry_after(self, client_id: str) -> int | None:
        client_key = sha256(client_id.encode("utf-8")).hexdigest()
        retry_after = await self._client.eval(
            _REDIS_RATE_LIMIT_SCRIPT,
            1,
            f"milu:rate-limit:{client_key}",
            self._window_milliseconds,
            self._limit,
            uuid4().hex,
        )
        return int(retry_after) or None


class PayloadLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        max_body_bytes: int = MAX_CHAT_BODY_BYTES,
    ):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope.get("path") != CHAT_PATH
            or scope.get("type") not in {"http", "websocket"}
        ):
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http":
            await self._handle_http(scope, receive, send)
            return

        await self._handle_websocket(scope, receive, send)

    async def _handle_http(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("method") != "POST":
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for name, value in scope.get("headers", [])
                if name.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._body_too_large(send, self.max_body_bytes)
                    return
            except ValueError:
                pass

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return

            body.extend(message.get("body", b""))
            if len(body) > self.max_body_bytes:
                await self._body_too_large(send, self.max_body_bytes)
                return
            if not message.get("more_body", False):
                break

        first_message = True

        async def replay_body() -> dict:
            nonlocal first_message
            if first_message:
                first_message = False
                return {
                    "type": "http.request",
                    "body": bytes(body),
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, replay_body, send)

    async def _handle_websocket(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        async def limited_receive() -> dict:
            message = await receive()
            if message["type"] == "websocket.receive":
                payload = message.get("text")
                size = (
                    len(payload.encode("utf-8"))
                    if payload is not None
                    else len(message.get("bytes", b""))
                )
                if size > self.max_body_bytes:
                    await send({"type": "websocket.close", "code": 1009})
                    raise WebSocketDisconnect(code=1009)
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _body_too_large(send: Send, max_body_bytes: int) -> None:
        body = json.dumps(
            {
                "detail": (
                    f"Request body exceeds the {max_body_bytes}-byte limit."
                )
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send(
            {"type": "http.response.body", "body": body, "more_body": False}
        )


class ChatRateLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_limited_request(scope):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_id = client[0] if client else "unknown"
        limiter = scope["app"].state.rate_limiter

        try:
            retry_after = await limiter.retry_after(client_id)
        except RedisError:
            logging.exception("Rate-limit storage is unavailable")
            await self._unavailable(scope, receive, send)
            return

        if retry_after is None:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http":
            response = JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        await send({"type": "websocket.accept"})
        await send(
            {
                "type": "websocket.send",
                "text": json.dumps(
                    {
                        "type": "error",
                        "detail": "Rate limit exceeded. Please try again later.",
                    }
                ),
            }
        )
        await send({"type": "websocket.close", "code": 1013})

    @staticmethod
    async def _unavailable(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            response = JSONResponse(
                status_code=503,
                content={"detail": "Rate limiting is temporarily unavailable."},
            )
            await response(scope, receive, send)
            return

        await send({"type": "websocket.accept"})
        await send(
            {
                "type": "websocket.send",
                "text": json.dumps(
                    {
                        "type": "error",
                        "detail": "Rate limiting is temporarily unavailable.",
                    }
                ),
            }
        )
        await send({"type": "websocket.close", "code": 1013})

    @staticmethod
    def _is_limited_request(scope: Scope) -> bool:
        if scope.get("path") != CHAT_PATH:
            return False

        return (
            scope["type"] == "websocket"
            or (
                scope["type"] == "http"
                and scope.get("method") == "POST"
            )
        )
