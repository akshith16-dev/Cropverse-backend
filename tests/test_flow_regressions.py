from datetime import date
from uuid import uuid4


def _register(client, path, payload):
    response = client.post(path, json=payload)
    assert response.status_code in {201, 400}
    if response.status_code == 400:
        login = client.post(
            "/auth/login",
            data={"username": payload["email"], "password": payload["password"]},
        )
        assert login.status_code == 200
        return login.json()
    return response.json()


def _headers(token_response):
    return {"Authorization": f"Bearer {token_response['access_token']}"}


def _setup_marketplace_flow(client, suffix="flow"):
    admin = _register(
        client,
        "/auth/register/admin",
        {"name": "Flow Admin", "email": f"admin-{suffix}@example.com", "password": "Admin12345", "phone": "111"},
    )
    farmer = _register(
        client,
        "/auth/register/farmer",
        {
            "name": "Flow Farmer",
            "email": f"farmer-{suffix}@example.com",
            "password": "Farmer12345",
            "phone": "222",
            "village": "Village",
            "district": "Guntur",
            "soil_type": "loamy",
            "land_acres": 2,
        },
    )
    shop_one = _register(
        client,
        "/auth/register/shop",
        {
            "name": "Flow Shop One",
            "email": f"shop-one-{suffix}@example.com",
            "password": "Shop12345",
            "phone": "333",
            "shop_name": "Shop One",
            "location": "Guntur",
        },
    )
    shop_two = _register(
        client,
        "/auth/register/shop",
        {
            "name": "Flow Shop Two",
            "email": f"shop-two-{suffix}@example.com",
            "password": "Shop12345",
            "phone": "444",
            "shop_name": "Shop Two",
            "location": "Vijayawada",
        },
    )

    admin_headers = _headers(admin)
    farmer_headers = _headers(farmer)
    shop_one_headers = _headers(shop_one)
    shop_two_headers = _headers(shop_two)

    crop_response = client.post(
        "/crops/",
        headers=admin_headers,
        json={
            "crop_name": f"Audit Tomato {suffix}",
            "season": "kharif",
            "soil_suitability": "loamy",
            "avg_yield_per_acre": 1000,
            "min_price": 10,
            "max_price": 30,
            "cultivation_cost": 8,
        },
    )
    assert crop_response.status_code in {201, 400}
    crop_id = crop_response.json().get("id")
    if not crop_id:
        crop_id = next(crop["id"] for crop in client.get("/crops/").json() if crop["crop_name"] == f"Audit Tomato {suffix}")

    farmer_id = client.get("/farmers/me", headers=farmer_headers).json()["id"]
    assignment_response = client.post(
        "/assignments/",
        headers=admin_headers,
        json={"farmer_id": farmer_id, "crop_id": crop_id, "season": "kharif", "year": 2026},
    )
    assert assignment_response.status_code in {201, 400}
    if assignment_response.status_code == 201:
        assignment_id = assignment_response.json()["id"]
    else:
        assignments = client.get("/assignments/", headers=admin_headers).json()
        assignment_id = next(item["id"] for item in assignments if item["farmer_id"] == farmer_id and item["crop_id"] == crop_id)

    return {
        "admin": admin_headers,
        "farmer": farmer_headers,
        "shop_one": shop_one_headers,
        "shop_two": shop_two_headers,
        "crop_id": crop_id,
        "assignment_id": assignment_id,
    }


def test_marketplace_flow_security_and_inventory(client):
    flow = _setup_marketplace_flow(client, f"security-{uuid4().hex[:8]}")

    pending_baby = client.post(
        "/baby-crops/",
        headers=flow["farmer"],
        json={
            "assignment_id": flow["assignment_id"],
            "sowing_date": date.today().isoformat(),
            "expected_harvest": "2026-09-24",
            "quantity_kg": 50,
            "notes": "should require acceptance",
        },
    )
    assert pending_baby.status_code == 400

    accept = client.put(f"/assignments/{flow['assignment_id']}/status", headers=flow["farmer"], json={"status": "accepted"})
    assert accept.status_code == 200

    baby = client.post(
        "/baby-crops/",
        headers=flow["farmer"],
        json={
            "assignment_id": flow["assignment_id"],
            "sowing_date": date.today().isoformat(),
            "expected_harvest": "2026-09-24",
            "quantity_kg": 50,
            "notes": "ready",
        },
    )
    assert baby.status_code == 200

    marketplace = client.get("/baby-crops/marketplace", headers=flow["shop_one"])
    assert marketplace.status_code == 200
    baby_id = next(item["id"] for item in marketplace.json() if item["assignment_id"] == flow["assignment_id"])

    bad_stage = client.put(f"/baby-crops/{baby_id}/stage", headers=flow["farmer"], json={"growth_stage": "bad-stage"})
    assert bad_stage.status_code == 400

    oversell = client.post(
        "/orders/",
        headers=flow["shop_one"],
        json={"baby_crop_id": baby_id, "quantity_kg": 999, "price_per_kg": 20, "order_type": "spot"},
    )
    assert oversell.status_code == 400

    order = client.post(
        "/orders/",
        headers=flow["shop_one"],
        json={"baby_crop_id": baby_id, "quantity_kg": 10, "price_per_kg": 20, "order_type": "spot"},
    )
    assert order.status_code == 200
    order_id = order.json()["order"]["id"]
    assert client.get(f"/orders/{order_id}", headers=flow["shop_two"]).status_code == 403

    demand = client.post(
        "/demand/",
        headers=flow["shop_one"],
        json={"crop_id": flow["crop_id"], "quantity_kg": 100, "required_by": "2026-07-24"},
    )
    assert demand.status_code == 200
    demand_id = demand.json()["demand"]["id"]
    assert client.get(f"/demand/{demand_id}", headers=flow["shop_two"]).status_code == 403
    assert client.put(f"/demand/{demand_id}", headers=flow["shop_two"], json={"quantity_kg": 999}).status_code == 403


def test_farmer_order_lifecycle_and_notifications(client):
    flow = _setup_marketplace_flow(client, f"orders-{uuid4().hex[:8]}")
    assert client.put(f"/assignments/{flow['assignment_id']}/status", headers=flow["farmer"], json={"status": "accepted"}).status_code == 200
    assert client.post(
        "/baby-crops/",
        headers=flow["farmer"],
        json={
            "assignment_id": flow["assignment_id"],
            "sowing_date": date.today().isoformat(),
            "expected_harvest": "2026-09-24",
            "quantity_kg": 75,
            "notes": "order lifecycle",
        },
    ).status_code == 200
    marketplace = client.get("/baby-crops/marketplace", headers=flow["shop_one"]).json()
    baby_id = next(item["id"] for item in marketplace if item["assignment_id"] == flow["assignment_id"])

    order = client.post(
        "/orders/",
        headers=flow["shop_one"],
        json={"baby_crop_id": baby_id, "quantity_kg": 15, "price_per_kg": 20, "order_type": "spot"},
    )
    assert order.status_code == 200
    order_id = order.json()["order"]["id"]

    farmer_orders = client.get("/orders/me", headers=flow["farmer"])
    assert farmer_orders.status_code == 200
    assert any(item["id"] == order_id for item in farmer_orders.json())

    assert client.put(f"/orders/{order_id}/accept", headers=flow["farmer"]).json()["order"]["status"] == "confirmed"
    assert client.put(f"/orders/{order_id}/dispatch", headers=flow["farmer"]).json()["order"]["status"] == "dispatched"
    assert client.put(f"/orders/{order_id}/deliver", headers=flow["farmer"]).json()["order"]["status"] == "delivered"

    shop_notifications = client.get("/notifications/", headers=flow["shop_one"])
    assert shop_notifications.status_code == 200
    assert any("delivered" in item["message"] for item in shop_notifications.json())


def test_farmer_can_reject_pending_order(client):
    flow = _setup_marketplace_flow(client, f"reject-{uuid4().hex[:8]}")
    assert client.put(f"/assignments/{flow['assignment_id']}/status", headers=flow["farmer"], json={"status": "accepted"}).status_code == 200
    assert client.post(
        "/baby-crops/",
        headers=flow["farmer"],
        json={
            "assignment_id": flow["assignment_id"],
            "sowing_date": date.today().isoformat(),
            "expected_harvest": "2026-09-24",
            "quantity_kg": 25,
            "notes": "reject lifecycle",
        },
    ).status_code == 200
    marketplace = client.get("/baby-crops/marketplace", headers=flow["shop_one"]).json()
    baby_id = next(item["id"] for item in marketplace if item["assignment_id"] == flow["assignment_id"])
    order = client.post(
        "/orders/",
        headers=flow["shop_one"],
        json={"baby_crop_id": baby_id, "quantity_kg": 5, "price_per_kg": 20, "order_type": "spot"},
    )
    order_id = order.json()["order"]["id"]
    rejected = client.put(f"/orders/{order_id}/reject", headers=flow["farmer"])
    assert rejected.status_code == 200
    assert rejected.json()["order"]["status"] == "rejected"


def test_admin_demand_lifecycle_and_high_demand(client):
    flow = _setup_marketplace_flow(client, f"demand-{uuid4().hex[:8]}")
    demand = client.post(
        "/demand/",
        headers=flow["shop_one"],
        json={"crop_id": flow["crop_id"], "quantity_kg": 125, "required_by": "2026-07-24"},
    )
    assert demand.status_code == 200
    demand_id = demand.json()["demand"]["id"]

    assert client.put(f"/demand/{demand_id}/approve", headers=flow["admin"]).json()["demand"]["status"] == "approved"
    assert client.put(f"/demand/{demand_id}/planned", headers=flow["admin"]).json()["demand"]["status"] == "planned"
    high_demand = client.get("/demand/insights/high-demand", headers=flow["farmer"])
    assert high_demand.status_code == 200
    assert any(item["quantity_kg"] >= 125 for item in high_demand.json())

    shop_notifications = client.get("/notifications/", headers=flow["shop_one"])
    assert any("planned" in item["message"] for item in shop_notifications.json())
