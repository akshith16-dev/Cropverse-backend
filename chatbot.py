import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth import get_current_user
from config import settings
from gemini_client import generate_gemini_text

logger = logging.getLogger("cropverse")
AI_FALLBACK_REPLY = "I'm currently unable to contact the AI service. Please try again in a few moments."

router = APIRouter(
    prefix="/chatbot",
    tags=["Chatbot"]
)

class ChatRequest(BaseModel):
    message: str
    language: str = "English"
    context: str = ""


@router.post("/chat")
async def chat(
    data: ChatRequest,
    current_user=Depends(get_current_user)
):
    if not settings.GEMINI_API_KEY.strip():
        return {
            "reply": AI_FALLBACK_REPLY
        }

    try:
        prompt = f"""

        You are Cropverse AI, an expert Indian agriculture advisor.

        You are an agricultural advisor helping Indian farmers.

        Rules:
        1. Give practical farming advice.
        2. Mention common causes.
        3. Give actionable steps.
        4. Give prevention tips.
        5. Keep answers under 200 words.
        6. Focus on Indian farming conditions.
        7. Cover disease diagnosis, fertilizer suggestions, weather precautions,
           harvest planning, and crop recommendations when relevant.
        8. Reply in {data.language}. Use simple language.

        Additional context: {data.context}

        Question:
        {data.message}
        """

        answer = await generate_gemini_text(prompt, "gemini-2.5-flash-lite")

        if not answer:
            return {
                "reply": AI_FALLBACK_REPLY
            }

        return {
            "reply": answer
        }

    except Exception as exc:
        logger.warning("Gemini advisor request failed: %s", exc.__class__.__name__)
        return {
            "reply": AI_FALLBACK_REPLY
        }
