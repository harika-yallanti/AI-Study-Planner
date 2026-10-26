from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_login_page_loads():
    response = client.get("/login", follow_redirects=False)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_forgot_password_page_loads():
    response = client.get("/forgot-password", follow_redirects=False)

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_unknown_route_returns_404():
    response = client.get("/this-route-does-not-exist")

    assert response.status_code == 404

def test_register_user(client):
    response = client.post(
        "/users/register",
        json={
            "name": "Backend Test User",
            "email": "backend.test@example.com",
            "password": "TestPassword123"
        }
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Backend Test User"
    assert data["email"] == "backend.test@example.com"


def test_register_duplicate_email(client):
    user_data = {
        "name": "Duplicate Test User",
        "email": "duplicate.test@example.com",
        "password": "TestPassword123"
    }

    first_response = client.post(
        "/users/register",
        json=user_data
    )

    assert first_response.status_code == 201

    second_response = client.post(
        "/users/register",
        json=user_data
    )

    assert second_response.status_code == 400
    assert "already registered" in second_response.json()["detail"].lower()


def test_login_success(client):
    user_data = {
        "name": "Login Test User",
        "email": "login.test@example.com",
        "password": "TestPassword123"
    }

    register_response = client.post(
        "/users/register",
        json=user_data
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/users/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"]
        }
    )

    assert login_response.status_code == 200

    data = login_response.json()

    assert data["message"] == "Login successful"
    assert data["user_id"] > 0
    assert data["email"] == user_data["email"]
    assert data["name"] == user_data["name"]
    assert data["role"] == "student"


def test_login_wrong_password(client):
    user_data = {
        "name": "Wrong Password User",
        "email": "wrong.password@example.com",
        "password": "TestPassword123"
    }

    register_response = client.post(
        "/users/register",
        json=user_data
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/users/login",
        json={
            "email": user_data["email"],
            "password": "WrongPassword123"
        }
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"


def test_login_unknown_email(client):
    login_response = client.post(
        "/users/login",
        json={
            "email": "does.not.exist@example.com",
            "password": "TestPassword123"
        }
    )

    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password"


def test_login_creates_session(client):
    user_data = {
        "name": "Session Test User",
        "email": "session.test@example.com",
        "password": "TestPassword123"
    }

    register_response = client.post(
        "/users/register",
        json=user_data
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/users/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"]
        }
    )
    assert login_response.status_code == 200

    # Verify the session cookie is created.
    assert "session" in client.cookies


def test_logout_clears_session(client):
    user_data = {
        "name": "Logout Test User",
        "email": "logout.test@example.com",
        "password": "TestPassword123"
    }

    register_response = client.post(
        "/users/register",
        json=user_data
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/users/login",
        json={
            "email": user_data["email"],
            "password": user_data["password"]
        }
    )
    assert login_response.status_code == 200
    assert "session" in client.cookies

    logout_response = client.post("/users/logout")

    assert logout_response.status_code == 200
    assert logout_response.json()["message"] == "Logout successful"

    # The logout response should clear the session cookie.
    assert "session" not in client.cookies
