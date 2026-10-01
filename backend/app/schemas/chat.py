"""backend/app/schemas/chat.py"""

from pydantic import BaseModel

from app.nlp.entities import Entities
from app.nlp.intent import Intent


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str
    intent: Intent
    entities: Entities
    parse_method: str  # "rules" or "llm"
    data: dict | None = None  # the verified structured result, for frontend cards
