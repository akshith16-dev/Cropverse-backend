from fastapi import APIRouter, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import os

from auth import get_current_user

load_dotenv()

genai.configure(
    api_key=os.getenv("GEMINI_API_KEY")
)

router = APIRouter(
    prefix="/chatbot",
    tags=["Chatbot"]
)

model = genai.GenerativeModel("gemini-2.5-flash-lite")


class ChatRequest(BaseModel):
    message: str


@router.post("/chat")
async def chat(
    data: ChatRequest,
    current_user=Depends(get_current_user)
):
    try:
        prompt = f"""

        You are Cropverse AI.

        You are an agricultural advisor helping Indian farmers.

        Rules:
        1. Give practical farming advice.
        2. Mention common causes.
        3. Give actionable steps.
        4. Give prevention tips.
        5. Keep answers under 200 words.
        6. Focus on Indian farming conditions.
        7. Avoid medical or unrelated advice.

        Question:
        {data.message}
        """

        response = model.generate_content(prompt)

        print("RESPONSE:", response)

        answer = getattr(response, "text", None)

        if not answer:
            return {
                "reply": "Gemini returned an empty response."
            }

        return {
            "reply": answer
        }

    except Exception as e:
        print("ERROR:", str(e))

        return {
            "reply": f"Gemini Error: {str(e)}"
        }
