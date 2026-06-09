import os
from fastapi import FastAPI
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from google import genai
from prompt_content import CONTEXTO_PORTFOLIO, PERSONALIDADE

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://alexandrelanga.github.io/minha-historia-na-web/"],
    allow_methods=["POST"],
    allow_headers=["*"],
)

class UserMessage(BaseModel):
    message: str

@app.post("/chat")
async def chat_assistant(data: UserMessage):
    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        return {"error": "API Key não configurada"}

    client = genai.Client(api_key=api_key)
    
    prompt_completo = f"Personalidade:\n{PERSONALIDADE}\n\nContexto sobre o desenvolvedor:\n{CONTEXTO_PORTFOLIO}\n\nPergunta do usuário: {data.message}"
    
    response = client.models.generate_content(
        model='gemini-2.5-flash-lite',
        contents=prompt_completo
    )
    return {"response": response.text}