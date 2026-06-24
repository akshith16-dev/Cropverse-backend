def test_reports_require_admin_authentication(client):
    response = client.get("/reports/farmers?format=pdf")
    assert response.status_code in {401, 403}
