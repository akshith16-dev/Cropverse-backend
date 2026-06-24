"""Small async Gemini REST client with hard network timeouts.

The older google-generativeai SDK exposes synchronous calls that can keep
worker threads alive after a timeout. For request/response API routes, a direct
HTTP call with a real timeout is easier to control and safer in production.
"""
import asyncio
import logging
from typing import Optional

import requests

from config import settings

logger = logging.getLogger("cropverse")


async def generate_gemini_text(prompt: str, model: str) -> Optional[str]:
    if not settings.GEMINI_API_KEY.strip():
        logger.info("Gemini request skipped: GEMINI_API_KEY is not configured")
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        f"?key={settings.GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    def request_text() -> Optional[str]:
        logger.info(
            "Gemini request payload: model=%s prompt_chars=%s contents=%s",
            model,
            len(prompt),
            len(payload["contents"]),
        )
        for attempt in range(2):
            response = requests.post(url, json=payload, timeout=settings.GEMINI_TIMEOUT_SECONDS)
            logger.info("Gemini response status: %s attempt=%s", response.status_code, attempt + 1)
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates") or []
            parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "".join(part.get("text", "") for part in parts).strip()
            if text:
                return text
            logger.warning("Gemini returned empty candidate text: model=%s attempt=%s", model, attempt + 1)
        return None

    try:
        return await asyncio.to_thread(request_text)
    except Exception as exc:
        logger.warning("Gemini request failed: %s", exc.__class__.__name__)
        return None
