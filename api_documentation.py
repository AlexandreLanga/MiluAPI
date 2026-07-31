TITLE = """Milu Chat Assistant API Documentation"""

DESCRIPTION = """
This API provides an endpoint for interacting with the Milu Chat Assistant.

Milu is a conversational AI designed to assist users with various queries about Minha História na Web project.

The assistant is powered by the Gemini-2.5-Flash-Lite model and is tailored to provide responses based on a specific personality and context related to the developer's portfolio.

Only accepts POST requests to the /chat endpoint with a JSON body containing a "message" field.

Not an open API, intended for use by the frontend of Minha História na Web project.

Milu's responses are generated based on the retrieved context from the developer's portfolio. If the context does not contain the answer, Milu will politely inform the user that it specializes in presenting the Minha História na Web project and will not invent information.
"""

VERSION = "1.1.1"