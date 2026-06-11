import os
import logging

from fastapi import FastAPI, HTTPException
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from google import genai

from prompt_content import CONTEXTO_PORTFOLIO, PERSONALIDADE

load_dotenv()

logging.basicConfig(level=logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://alexandrelanga.github.io"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UserMessage(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


@app.post("/chat")
async def chat_assistant(data: UserMessage):
    try:
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise HTTPException(
                status_code=500,
                detail="Serviço temporariamente indisponível."
            )

        client = genai.Client(api_key=api_key)

        prompt_completo = f"""
Personalidade:
{PERSONALIDADE}

Contexto sobre o desenvolvedor:
{CONTEXTO_PORTFOLIO}

Pergunta do usuário:
{data.message}
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt_completo
        )

        if not response or not response.text:
            raise HTTPException(
                status_code=502,
                detail="Não foi possível gerar uma resposta no momento."
            )

        return {
            "success": True,
            "message": response.text
        }

    except HTTPException:
        raise

    except Exception as e:
        logging.exception("Erro ao processar chat")

        return {
            "success": False,
            "message": (
                "Desculpe, ocorreu um erro temporário ao processar sua mensagem. "
                "Por favor, tente novamente em alguns instantes."
            ),
            "error": str(e) if os.getenv("ENV") == "development" else None
        }