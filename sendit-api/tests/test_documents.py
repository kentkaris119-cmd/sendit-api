import io


def get_auth_headers(client, test_user):
    client.post("/register", json=test_user)

    response = client.post(
        "/login",
        data={
            "username": test_user["username"],
            "password": test_user["password"]
        }
    )

    token = response.json()["access_token"]

    return {
        "Authorization": f"Bearer {token}"
    }


def test_upload_document(client, test_user):
    headers = get_auth_headers(client, test_user)

    file_data = io.BytesIO(b"Hello from pytest")

    response = client.post(
        "/documents/upload",
        headers=headers,
        files={
            "file": (
                "test.pdf",
                file_data,
                "application/pdf"
            )
        },
        data={
            "city": "Nairobi",
            "country": "Kenya",
            "description": "Testing upload"
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["message"] == "Document uploaded successfully"


def test_list_documents(client, test_user):
    headers = get_auth_headers(client, test_user)

    response = client.get(
        "/documents",
        headers=headers
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_document_not_found(client, test_user):
    headers = get_auth_headers(client, test_user)

    response = client.get(
        "/documents/99999",
        headers=headers
    )

    assert response.status_code == 404