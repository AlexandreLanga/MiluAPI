import os
import logging

from dotenv import load_dotenv
from fastapi import HTTPException
from google import genai

from prompt_content import CONTEXTO_PORTFOLIO, PERSONALIDADE, PORTFOLIO_CONTEXT, PERSONALITY

load_dotenv()

logging.basicConfig(level=logging.INFO)


def chat_assistant(message: str, language: str) -> dict:
    try:
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Au au! Parece que minha coleira de API não está configurada."
                    if language == "pt"
                    else "Woof woof! It seems like my API leash isn't set up."
                )
            )

        client = genai.Client(api_key=api_key)

        if language == "pt":
            prompt_completo = f"""
            Personalidade:
            {PERSONALIDADE}

            Contexto sobre o desenvolvedor:
            {CONTEXTO_PORTFOLIO}

            Pergunta do usuário:
            {message}
            """
        else:
            prompt_completo = f"""
            Personality:
            {PERSONALITY}

            Context about the developer:
            {PORTFOLIO_CONTEXT}

            User's question:
            {message}
            """

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=prompt_completo
        )

        if not response or not response.text:
            raise HTTPException(
                status_code=502,
                detail="Au au! Tentei pensar em uma resposta, mas não consegui. Estou latindo para os meus humanos para resolver isso o mais rápido possível!"
                if language == "pt"
                else "Woof woof! I tried to think of a response but couldn't come up with one. I'm barking at my humans to get this fixed as soon as possible!"
            )

        return {
            "success": True,
            "message": response.text
        }

    except HTTPException:
        raise

    except Exception as e:
        logging.exception("Erro ao processar chat" if language == "pt" else "Error processing chat")

        error_message = str(e).lower()

        if any(term in error_message for term in [
            "resource_exhausted",
            "quota",
            "429",
            "rate limit",
            "too many requests"
        ]):
            message = (
                "Oi! Sou a Milu 😵\n\n"
                "Recebi sua mensagem, mas estou atendendo muitas pessoas "
                "agora e meus recursos ficaram temporariamente indisponíveis.\n\n"
                "Tente novamente outra hora. Vou ficar feliz em continuar nossa conversa!"
            ) if language == "pt" else (
                "Hi! I'm Milu 😵\n\n"
                "I received your message, but I'm currently attending to many people "
                "and my resources have become temporarily unavailable.\n\n"
                "Please try again later. I'll be happy to continue our conversation!"
            )

        elif "timeout" in error_message:
            message = (
                "Oi! Sou a Milu 😵\n\n"
                "Demorei mais do que o esperado para pensar em uma resposta e a conexão expirou.\n\n"
                "Pode tentar enviar sua mensagem novamente?"
            ) if language == "pt" else (
                "Hi! I'm Milu 😵\n\n"
                "I took longer than expected to think of a response and the connection expired.\n\n"
                "Can you try sending your message again?"
            )

        elif any(term in error_message for term in [
            "api key",
            "permission",
            "unauthorized",
            "authentication"
        ]):
            message = (
                "Oi! Sou a Milu 😵\n\n"
                "Estou passando por uma manutenção interna no momento.\n\n"
                "Tente novamente mais tarde."
            ) if language == "pt" else (
                "Hi! I'm Milu 😵\n\n"
                "I'm undergoing internal maintenance at the moment.\n\n"
                "Please try again later."
            )

        else:
            message = (
                "Oi! Sou a Milu 😵\n\n"
                "Encontrei um probleminha inesperado enquanto processava sua mensagem.\n\n"
                "Pode tentar novamente outra hora?"
            ) if language == "pt" else (
                "Hi! I'm Milu 😵\n\n"
                "I encountered an unexpected issue while processing your message.\n\n"
                "Can you try again later?"
            )

        return {
            "error": True,
            "message": message
        }