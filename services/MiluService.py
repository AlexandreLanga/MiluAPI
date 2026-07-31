import os
import logging

from dotenv import load_dotenv
from fastapi import HTTPException
from google import genai

from prompts.personality_pt import PERSONALIDADE
from prompts.personality_en import PERSONALITY
from prompts.portifolio_context_pt import CONTEXTO_PORTFOLIO
from prompts.portifolio_context_en import PORTFOLIO_CONTEXT
from services.RagService import PortfolioRetriever, format_retrieved_context

load_dotenv()

logging.basicConfig(level=logging.INFO)

PORTUGUESE_RETRIEVER = PortfolioRetriever(CONTEXTO_PORTFOLIO)
ENGLISH_RETRIEVER = PortfolioRetriever(PORTFOLIO_CONTEXT)


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
            retrieved_context = format_retrieved_context(
                PORTUGUESE_RETRIEVER.retrieve(message),
                "Nenhum trecho específico foi recuperado para esta pergunta.",
            )
            prompt_completo = f"""
            Personalidade:
            {PERSONALIDADE}

            Você é a assistente do portfólio de Alexandre Langa. Sua base de
            conhecimento é exclusivamente o contexto recuperado abaixo. Se ele
            não trouxer a resposta, diga educadamente que sua especialidade é
            apresentar o projeto Minha História na Web e não invente informações.

            Contexto recuperado para esta pergunta:
            {retrieved_context}

            Pergunta do usuário:
            {message}

            IMPORTANTE:
            - Sempre responda em português, independentemente do idioma usado pelo usuário.
            - Responda naturalmente, sem Markdown, e de forma simples.
            - Para perguntas sobre como as funcionalidades foram desenvolvidas,
              indique https://github.com/AlexandreLanga/minha-historia-na-web.
            """
        else:
            retrieved_context = format_retrieved_context(
                ENGLISH_RETRIEVER.retrieve(message),
                "No specific portfolio information was retrieved for this question.",
            )
            prompt_completo = f"""
            Personality:
            {PERSONALITY}

            You are the assistant for Alexandre Langa's portfolio. Your knowledge
            is limited to the retrieved context below. If it does not contain the
            answer, politely say that your specialty is presenting the Minha
            História na Web project and do not invent information.

            Retrieved context for this question:
            {retrieved_context}

            User's question:
            {message}

            IMPORTANT:
            - Always answer in English regardless of the language used by the user.
            - Respond naturally, without Markdown, using simple language.
            - For questions about how features were developed, point to
              https://github.com/AlexandreLanga/minha-historia-na-web.
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

        raise HTTPException(
            status_code=503,
            detail=message
        )