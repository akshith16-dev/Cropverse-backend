def test_login_rejects_unknown_user(client):
    response = client.post(
        "/auth/login",
        data={"username": "missing@example.com", "password": "NoUser123"},
    )
    assert response.status_code == 401


def test_registration_rejects_weak_password(client):
    response = client.post(
        "/auth/register/admin",
        json={"name": "Admin", "email": "admin@example.com", "password": "weak", "phone": ""},
    )
    assert response.status_code == 422
