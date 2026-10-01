"""backend/app/routers/chat.py"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.nlp.llm_client import GroqClient
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import chat_service

router = APIRouter(prefix="/api/chat", tags=["chat"])


def get_llm_client():
    """Only build a real Groq client if a key is actually configured --
    otherwise the chat service runs in fully deterministic template mode
    (see docs/limitations.md)."""
    settings = get_settings()
    if settings.groq_api_key:
        return GroqClient()
    return None


@router.post("", response_model=ChatResponse)
def chat(body: ChatRequest, db: Session = Depends(get_db)):
    llm_client = get_llm_client()
    return chat_service.handle_chat_message(db, body.message, llm_client=llm_client)
