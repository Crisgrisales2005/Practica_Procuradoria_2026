"""RAG local: Chroma embebido + sentence-transformers. Sin LangChain ni Gemini."""

from backend.rag.retrieve import Hit, recuperar

__all__ = ["Hit", "recuperar"]
