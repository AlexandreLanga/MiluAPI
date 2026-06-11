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
    allow_methods=["POST"],
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

        error_message = str(e).lower()

        # Limite de uso / cota do Gemini
        if any(term in error_message for term in [
            "resource_exhausted",
            "quota",
            "429",
            "rate limit",
            "too many requests"
        ]):
            return {
                "success": False,
                "message": (
                    "Oi! Sou a Milu 😊\n\n"
                    "Recebi sua mensagem, mas estou atendendo muitas pessoas "
                    "agora e meus recursos ficaram temporariamente indisponíveis.\n\n"
                    "Tente novamente daqui a alguns minutos. Vou ficar feliz em continuar nossa conversa!"
                )
            }

        # Timeout
        if "timeout" in error_message:
            return {
                "success": False,
                "message": (
                    "Oi! Sou a Milu 😊\n\n"
                    "Demorei mais do que o esperado para pensar em uma resposta e a conexão expirou.\n\n"
                    "Pode tentar enviar sua mensagem novamente?"
                )
            }

        # Problemas de autenticação
        if any(term in error_message for term in [
            "api key",
            "permission",
            "unauthorized",
            "authentication"
        ]):
            return {
                "success": False,
                "message": (
                    "Oi! Sou a Milu 😊\n\n"
                    "Estou passando por uma manutenção interna no momento.\n\n"
                    "Tente novamente mais tarde."
                )
            }

        # Erro genérico
        return {
            "success": False,
            "message": (
                "Oi! Sou a Milu 😊\n\n"
                "Encontrei um probleminha inesperado enquanto processava sua mensagem.\n\n"
                "Pode tentar novamente em alguns instantes?"
            )
        }