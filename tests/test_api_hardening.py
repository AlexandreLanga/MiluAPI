import asyncio
from concurrent.futures import ThreadPoolExecutor
import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import services.MiluService as milu_service
import main
from main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("RATE_LIMIT_REDIS_URL", raising=False)
    with TestClient(app) as test_client:
        yield test_client


def test_rejects_oversized_http_payload(client):
    response = client.post(
        "/chat",
        content=b"x" * (16 * 1024 + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_rate_limit_returns_retry_after_header(client):
    payload = {"message": "Olá", "language": "pt"}

    for _ in range(10):
        response = client.post("/chat", json=payload)
        assert response.status_code == 500

    response = client.post("/chat", json=payload)

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) > 0


def test_redis_environment_variable_is_ignored(monkeypatch):
    monkeypatch.setenv(
        "RATE_LIMIT_REDIS_URL",
        "redis://this-host-does-not-exist:6379/0",
    )

    with TestClient(app) as test_client:
        response = test_client.get("/healthz")

        assert response.status_code == 200
        assert isinstance(app.state.rate_limiter, main.InMemoryRateLimiter)


def test_rejects_oversized_websocket_payload(client):
    with client.websocket_connect("/chat") as websocket:
        websocket.send_text("x" * (16 * 1024 + 1))
        with pytest.raises(WebSocketDisconnect) as disconnect:
            websocket.receive_text()

    assert disconnect.value.code == 1009


def test_websocket_does_not_expose_unexpected_exception(client, monkeypatch):
    async def fail_stream(*_args, **_kwargs):
        del _args, _kwargs
        yield None
        raise RuntimeError("internal provider detail")

    monkeypatch.setattr(milu_service, "chat_assistant_stream", fail_stream)

    with client.websocket_connect("/chat") as websocket:
        websocket.send_json({"message": "Olá", "language": "pt"})
        response = json.loads(websocket.receive_text())

    assert response["type"] == "error"
    assert "internal provider detail" not in response["detail"]


def test_concurrent_http_requests_respect_gemini_capacity(
    client,
    monkeypatch,
):
    active = 0
    maximum_active = 0

    async def fake_chat(message, language, gemini_client):
        nonlocal active, maximum_active
        del message, language, gemini_client
        active += 1
        maximum_active = max(maximum_active, active)
        await asyncio.sleep(0.05)
        active -= 1
        return {"success": True, "message": "ok"}

    monkeypatch.setattr(main, "chat_assistant", fake_chat)
    payload = {"message": "Olá", "language": "pt"}

    with ThreadPoolExecutor(max_workers=10) as executor:
        responses = list(
            executor.map(lambda _: client.post("/chat", json=payload), range(10))
        )

    assert all(response.status_code == 200 for response in responses)
    assert 1 < maximum_active <= 5
