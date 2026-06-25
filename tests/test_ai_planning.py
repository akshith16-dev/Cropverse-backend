from datetime import date
from uuid import uuid4


def _register(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in {200, 201, 400}
    if response.status_code == 400:
        login = client.post("/auth/login", data={"username": payload["email"], "password": payload["password"]})
        assert login.status_code == 200
        return login.json()
    return response.json()


def _headers(token_response):
    return {"Authorization": f"Bearer {token_response['access_token']}"}


def _setup(client, suffix):
    admin = _register(
        client,
        "/auth/register/admin",
        {"name": "AI Admin", "email": f"ai-admin-{suffix}@example.com", "password": "Admin12345", "phone": "100"},
    )
    farmer = _register(
        client,
        "/auth/register/farmer",
        {
            "name": "AI Farmer",
            "email": f"ai-farmer-{suffix}@example.com",
            "password": "Farmer12345",
            "phone": "200",
            "village": "Village",
            "district": "Guntur",
            "soil_type": "loamy",
            "land_acres": 2,
        },
    )
    shop = _register(
        client,
        "/auth/register/shop",
        {
            "name": "AI Shop",
            "email": f"ai-shop-{suffix}@example.com",
            "password": "Shop12345",
            "phone": "300",
            "shop_name": "AI Shop",
            "location": "Guntur",
        },
    )
    admin_headers = _headers(admin)
    farmer_headers = _headers(farmer)
    shop_headers = _headers(shop)
    farmer_id = client.get("/farmers/me", headers=farmer_headers).json()["id"]
    return admin_headers, farmer_headers, shop_headers, farmer_id


def _crop(client, headers, name, season="kharif", soil="loamy", yield_per_acre=1000, min_price=10, max_price=30, cost=8):
    response = client.post(
        "/crops/",
        headers=headers,
        json={
            "crop_name": name,
            "season": season,
            "soil_suitability": soil,
            "avg_yield_per_acre": yield_per_acre,
            "min_price": min_price,
            "max_price": max_price,
            "cultivation_cost": cost,
        },
    )
    assert response.status_code in {201, 400}
    if response.status_code == 201:
        return response.json()["id"]
    return next(item["id"] for item in client.get("/crops/").json() if item["crop_name"] == name)


def test_recommendation_engine_uses_demand_and_saves_history(client):
    suffix = uuid4().hex[:8]
    admin, _, shop, farmer_id = _setup(client, suffix)
    tomato_id = _crop(client, admin, f"Planning Tomato {suffix}", max_price=60)
    _crop(client, admin, f"Planning Millet {suffix}", soil="sandy", max_price=15)

    demand = client.post(
        "/demand/",
        headers=shop,
        json={"crop_id": tomato_id, "quantity_kg": 5000, "required_by": "2026-08-01"},
    )
    assert demand.status_code == 200

    response = client.post(f"/ai/recommend-crops/{farmer_id}", headers=admin)
    assert response.status_code == 200
    recommendations = response.json()
    assert len(recommendations) >= 2
    tomato = next(item for item in recommendations if item["crop"] == f"Planning Tomato {suffix}")
    assert "High demand" in tomato["reasons"]
    assert tomato["expected_profit"] > 0

    history = client.get(f"/ai/recommendations?farmer_id={farmer_id}", headers=admin)
    assert history.status_code == 200
    assert any(item["crop"] == f"Planning Tomato {suffix}" for item in history.json())


def test_auto_assignment_creates_pending_assignment_and_notifications(client):
    suffix = uuid4().hex[:8]
    admin, farmer, _, farmer_id = _setup(client, suffix)
    _crop(client, admin, f"Auto Groundnut {suffix}", max_price=55)

    response = client.post(f"/ai/auto-assign/{farmer_id}", headers=admin)
    assert response.status_code == 200
    body = response.json()
    assert body["assignment_id"]
    assert body["recommendation"]["recommendation_type"] == "auto_assignment"

    assignments = client.get("/assignments/me", headers=farmer)
    assert any(item["id"] == body["assignment_id"] and item["status"] == "pending" for item in assignments.json())
    notifications = client.get("/notifications/", headers=farmer)
    assert any("auto-assigned" in item["message"] for item in notifications.json())


def test_crop_rotation_and_harvest_trigger_create_recommendations(client):
    suffix = uuid4().hex[:8]
    admin, farmer, _, farmer_id = _setup(client, suffix)
    rice_id = _crop(client, admin, f"Rice {suffix}", soil="loamy", max_price=28)
    _crop(client, admin, f"Groundnut {suffix}", soil="loamy", max_price=50)

    assignment = client.post(
        "/assignments/",
        headers=admin,
        json={"farmer_id": farmer_id, "crop_id": rice_id, "season": "kharif", "year": 2025},
    )
    assert assignment.status_code == 201

    rotation = client.post(f"/ai/crop-rotation/{farmer_id}", headers=admin)
    assert rotation.status_code == 200
    assert rotation.json()["recommendation_type"] == "rotation"
    assert any(reason in rotation.json()["reasons"] for reason in ["Rotation compatible", "Restores soil nitrogen"])

    assert client.put(f"/assignments/{assignment.json()['id']}/status", headers=farmer, json={"status": "accepted"}).status_code == 200
    baby = client.post(
        "/baby-crops/",
        headers=farmer,
        json={
            "assignment_id": assignment.json()["id"],
            "sowing_date": date.today().isoformat(),
            "expected_harvest": "2026-09-24",
            "quantity_kg": 25,
            "notes": "rotation trigger",
        },
    )
    assert baby.status_code == 200
    baby_id = next(item["id"] for item in client.get("/baby-crops/", headers=farmer).json() if item["assignment_id"] == assignment.json()["id"])
    stage = client.put(f"/baby-crops/{baby_id}/stage", headers=farmer, json={"growth_stage": "harvest"})
    assert stage.status_code == 200

    notifications = client.get("/notifications/", headers=farmer)
    assert any("AI has recommended" in item["message"] for item in notifications.json())
