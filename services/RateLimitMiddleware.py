from collections import deque
import json
from math import ceil
from threading import Lock
from time import monotonic

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
CHAT_PATH = "/chat"


class InMemoryRateLimiter:
    def __init__(self, limit: int, window_seconds: int):
        self._limit = limit
        self._window_seconds = window_seconds
        self._requests: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._checks = 0

    def retry_after(self, client_id: str) -> int | None:
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


class ChatRateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        limit: int = RATE_LIMIT_REQUESTS,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.app = app
        self._limiter = InMemoryRateLimiter(limit, window_seconds)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_limited_request(scope):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_id = client[0] if client else "unknown"
        retry_after = self._limiter.retry_after(client_id)
        if retry_after is None:
            await self.app(scope, receive, send)
            return

        if scope["type"] == "http":
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": "Limite de mensagens atingido. "
                    "Tente novamente em instantes."
                },
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
                        "detail": (
                            "Limite de mensagens atingido. "
                            f"Tente novamente em {retry_after} segundos."
                        ),
                    },
                    ensure_ascii=False,
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
