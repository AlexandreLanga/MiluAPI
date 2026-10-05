from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from services.RateLimitMiddleware import ChatRateLimitMiddleware
from services.MiluService import UserMessage, chat_assistant, websocket_chat
from api_documentation import TITLE, DESCRIPTION, VERSION

app = FastAPI(title=TITLE, description=DESCRIPTION, version=VERSION)

app.add_middleware(ChatRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://alexandrelanga.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat")
def chat_assistant_endpoint(data: UserMessage):
    return chat_assistant(data.message, data.language)


@app.websocket("/chat")
async def websocket_chat_route(websocket: WebSocket):
    await websocket_chat(websocket)
