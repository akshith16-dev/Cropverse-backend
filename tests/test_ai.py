import chatbot


def test_crop_recommendation_requires_authentication(client):
    response = client.post(
        "/ai/recommend-crop",
        json={"soil_type": "loamy", "district": "Guntur", "season": "kharif", "land_acres": 2},
    )
    assert response.status_code in {401, 403}


def _farmer_token(client, email="ai-farmer@example.com"):
    response = client.post(
        "/auth/register/farmer",
        json={
            "name": "AI Farmer",
            "email": email,
            "password": "Farmer12345",
            "phone": "123",
            "village": "Village",
            "district": "Guntur",
            "soil_type": "loamy",
            "land_acres": 1,
        },
    )
    if response.status_code == 400:
        response = client.post(
            "/auth/login",
            data={"username": email, "password": "Farmer12345"},
        )
    assert response.status_code == 200 or response.status_code == 201
    return response.json()["access_token"]


def test_chatbot_returns_fallback_without_api_key(client):
    token = _farmer_token(client)
    response = client.post(
        "/chatbot/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": "How do I protect tomatoes?"},
    )
    assert response.status_code == 200
    assert "Gemini returned an empty response" not in response.json()["reply"]
    assert "unable to contact" in response.json()["reply"]


def test_chatbot_empty_gemini_response_uses_fallback(client, monkeypatch):
    token = _farmer_token(client, "advisor-farmer@example.com")

    async def empty_response(prompt, model):
        return None

    monkeypatch.setattr(chatbot.settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(chatbot, "generate_gemini_text", empty_response)

    response = client.post(
        "/chatbot/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "message": "My crop has leaf spots",
            "language": "English",
            "context": "Advanced farming advisor",
        },
    )
    assert response.status_code == 200
    assert response.json()["reply"] == chatbot.AI_FALLBACK_REPLY
