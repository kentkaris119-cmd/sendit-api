
def test_register_user(client, test_user):
    response = client.post("/register", json=test_user)

    assert response.status_code == 201

    data = response.json()

    assert data["user"]["username"] == test_user["username"]
    assert data["user"]["email"] == test_user["email"]


def test_duplicate_registration(client, test_user):
    client.post("/register", json=test_user)

    response = client.post("/register", json=test_user)

    assert response.status_code == 409


def test_login(client, test_user):
    client.post("/register", json=test_user)

    response = client.post(
        "/login",
        data={
            "username": test_user["username"],
            "password": test_user["password"]
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_invalid_login(client, test_user):
    client.post("/register", json=test_user)

    response = client.post(
        "/login",
        data={
            "username": test_user["username"],
            "password": "wrongpassword"
        }
    )

    assert response.status_code == 401

