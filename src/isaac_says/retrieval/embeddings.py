"""Creates the embedding model, which turns text into numbers for searching."""

from langchain_openai import OpenAIEmbeddings

from isaac_says.config import Settings


def make_embeddings(settings: Settings) -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        model=settings.embedding_model,
        api_key=settings.require_openai_key(),
        # A short timeout and retries, because requests sometimes stall.
        timeout=settings.llm_timeout_seconds,
        max_retries=3,
    )
