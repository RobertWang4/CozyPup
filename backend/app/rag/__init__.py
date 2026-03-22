"""RAG (Retrieval-Augmented Generation) framework for CozyPup."""

from app.rag.assembler import assemble_rag_context
from app.rag.intent import needs_retrieval
from app.rag.writer import write_calendar_event, write_chat_turn

__all__ = [
    "assemble_rag_context",
    "needs_retrieval",
    "write_chat_turn",
    "write_calendar_event",
]
