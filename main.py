from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from services.MiluService import chat_assistant
from api_documentation import TITLE, DESCRIPTION, VERSION

app = FastAPI(title=TITLE, description=DESCRIPTION, version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://alexandrelanga.github.io"],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["*"],
)


class UserMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


@app.post("/chat")
async def chat_assistant_endpoint(data: UserMessage, language: str):
    return chat_assistant(data.message, language)