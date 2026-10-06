TITLE = """Milu Chat Assistant API Documentation"""

DESCRIPTION = """
This API provides an endpoint for interacting with the Milu Chat Assistant.

Milu is a conversational AI designed to assist users with various queries about Minha História na Web project.

The assistant is powered by the Gemini-2.5-Flash-Lite model and is tailored to provide responses based on a specific personality and context related to the developer's portfolio.

Accepts POST requests and WebSocket connections at /chat. The HTTP JSON body contains "message" and "language" fields. Each WebSocket connection sends one JSON message with the same fields and receives chunk, done, or error events.

Not an open API, intended for use by the frontend of Minha História na Web project.

Milu's responses are generated based on the retrieved context from the developer's portfolio. If the context does not contain the answer, Milu will politely inform the user that it specializes in presenting the Minha História na Web project and will not invent information.

The API limits request payloads to 16 KiB, applies per-IP rate limits, and caps concurrent requests to the Gemini provider. Configure RATE_LIMIT_REDIS_URL to share rate-limit state across workers and replicas.
"""

VERSION = "1.1.1"