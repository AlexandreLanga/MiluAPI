from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

_STOP_WORDS = {
    "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos",
    "e", "em", "esta", "este", "eu", "me", "na", "nas", "no", "nos", "o",
    "os", "ou", "para", "por", "que", "se", "sobre", "um", "uma", "the", "and",
    "are", "at", "for", "from", "in", "is", "of", "on", "or", "to", "what", "who",
    "with", "your",
}

@dataclass(frozen=True)
class DocumentChunk:
    title: str
    content: str
    terms: Counter[str]

def _tokenize(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", text.lower())
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return [
        token for token in re.findall(r"[a-z0-9+#.]+", normalized)
        if len(token) > 1 and token not in _STOP_WORDS
    ]

def _split_sections(context: str) -> list[tuple[str, str]]:
    """Divide o conteúdo nas seções Markdown usadas em prompt_content.py."""
    sections = re.split(r"(?m)^# ", context.strip())
    result = []
    for section in sections:
        if not section.strip():
            continue
        title, _, content = section.partition("\n")
        result.append((title.strip(), content.strip()))
    return result

class PortfolioRetriever:
    def __init__(self, context: str):
        self._chunks = tuple(
            DocumentChunk(
                title=title,
                content=content,
                terms=Counter(_tokenize(f"{title} {content}")),
            )
            for title, content in _split_sections(context)
            # Estas seções são regras de comportamento, não conhecimento a ser
            # pesquisado. Elas permanecem no prompt-base do serviço.
            if "INSTRU" not in unicodedata.normalize("NFKD", title).upper()
        )

    def retrieve(self, question: str, limit: int = 3) -> list[DocumentChunk]:
        query_terms = _tokenize(question)
        if not query_terms:
            return []

        query = Counter(query_terms)
        ranked: list[tuple[float, DocumentChunk]] = []
        for chunk in self._chunks:
            # A repetição de um termo no documento aumenta levemente sua relevância,
            # sem permitir que uma seção longa domine apenas pelo tamanho.
            score = sum(
                query_count * (1 + min(chunk.terms[term], 3))
                for term, query_count in query.items()
                if term in chunk.terms
            )
            title_terms = set(_tokenize(chunk.title))
            # O título representa o assunto principal do trecho e por isso tem
            # mais peso que uma menção incidental dentro de outra seção.
            score += 5 * sum(query_count for term, query_count in query.items() if term in title_terms)
            if score:
                ranked.append((score, chunk))

        ranked.sort(key=lambda item: item[0], reverse=True)
        return [chunk for _, chunk in ranked[:limit]]

def format_retrieved_context(
    chunks: list[DocumentChunk], empty_context_message: str
) -> str:
    if not chunks:
        return empty_context_message

    return "\n\n".join(
        f"## {chunk.title}\n{chunk.content}" for chunk in chunks
    )