def test_upload_requires_authentication(client):
    response = client.post(
        "/upload/image",
        files={"file": ("crop.png", b"\x89PNG\r\n\x1a\nsample", "image/png")},
    )
    assert response.status_code == 401
