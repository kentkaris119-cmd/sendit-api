def test_404_endpoint(client):
    response = client.get("/this-endpoint-does-not-exist")

    assert response.status_code == 404


def test_unauthorized_documents(client):
    response = client.get("/documents")

    assert response.status_code == 401


def test_unauthorized_upload(client):
    response = client.post("/documents/upload")

    print(response.status_code)
    print(response.text)

    assert response.status_code in [401, 422]