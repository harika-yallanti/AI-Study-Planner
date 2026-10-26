import hashlib

from datetime import datetime, timedelta

from sqlalchemy import text

from app.models import User
from app.database import SessionLocal
from app import password_reset as password_reset_module
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.password_reset import send_password_reset_email


def test_reset_password_page_rejects_missing_token():
    client = TestClient(app)

    response = client.get(
        "/reset-password",
        follow_redirects=False
    )

    assert response.status_code == 200
    assert "Reset Password" in response.text
    assert "name=\"token\"" not in response.text


def test_reset_password_page_rejects_oversized_token():
    client = TestClient(app)

    response = client.get(
        "/reset-password",
        params={"token": "x" * 201},
        follow_redirects=False
    )

    assert response.status_code == 200
    assert "Reset Password" in response.text
    assert "name=\"token\"" not in response.text


def test_reset_password_rejects_oversized_posted_token():
    client = TestClient(app)

    response = client.post(
        "/reset-password",
        data={
            "token": "x" * 201,
            "new_password": "NewPassword123",
            "confirm_password": "NewPassword123",
        },
        follow_redirects=False
    )

    assert response.status_code == 400


def test_reset_password_rejects_mismatched_passwords():
    client = TestClient(app)

    with patch("app.main.reset_user_password") as reset_mock:
        response = client.post(
            "/reset-password",
            data={
                "token": "test-token",
                "new_password": "NewPassword123",
                "confirm_password": "DifferentPassword123",
            },
            follow_redirects=False
        )

    assert response.status_code == 400
    reset_mock.assert_not_called()


def test_reset_password_rejects_password_shorter_than_8_characters():
    client = TestClient(app)

    with patch("app.main.reset_user_password") as reset_mock:
        response = client.post(
            "/reset-password",
            data={
                "token": "test-token",
                "new_password": "Short7!",
                "confirm_password": "Short7!",
            },
            follow_redirects=False
        )

    assert response.status_code == 400
    reset_mock.assert_not_called()


def test_reset_password_rejects_password_longer_than_128_characters():
    client = TestClient(app)
    long_password = "A" * 129

    with patch("app.main.reset_user_password") as reset_mock:
        response = client.post(
            "/reset-password",
            data={
                "token": "test-token",
                "new_password": long_password,
                "confirm_password": long_password,
            },
            follow_redirects=False
        )

    assert response.status_code == 400
    reset_mock.assert_not_called()


def test_reset_password_rejects_invalid_token():
    client = TestClient(app)

    with patch("app.main.reset_user_password", return_value=False) as reset_mock:
        response = client.post(
            "/reset-password",
            data={
                "token": "invalid-token",
                "new_password": "NewPassword123",
                "confirm_password": "NewPassword123",
            },
            follow_redirects=False
        )

    assert response.status_code == 400
    reset_mock.assert_called_once_with(
        "invalid-token",
        "NewPassword123"
    )

def create_test_reset_token(client, email, token, expires_at, used_at=None):
    register_response = client.post(
        "/users/register",
        json={
            "name": "Password Reset Test User",
            "email": email,
            "password": "OldPassword123",
        },
    )
    assert register_response.status_code == 201

    user_id = register_response.json()["id"]

    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    db = password_reset_module.SessionLocal()

    try:
        db.execute(
            text("""
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at, used_at)
                VALUES
                    (:user_id, :token_hash, :expires_at, :used_at)
            """),
            {
                "user_id": user_id,
                "token_hash": token_hash,
                "expires_at": expires_at,
                "used_at": used_at,
            },
        )
        db.commit()
    finally:
        db.close()

    return user_id

def test_reset_password_rejects_expired_token(client):
    token = "expired-reset-token"

    create_test_reset_token(
        client,
        "expired.reset@example.com",
        token,
        datetime.utcnow() - timedelta(minutes=1),
    )

    assert password_reset_module.reset_user_password(
        token,
        "NewPassword123",
    ) is False


def test_reset_password_rejects_already_used_token(client):
    token = "used-reset-token"

    create_test_reset_token(
        client,
        "used.reset@example.com",
        token,
        datetime.utcnow() + timedelta(minutes=10),
        used_at=datetime.utcnow(),
    )

    assert password_reset_module.reset_user_password(
        token,
        "NewPassword123",
    ) is False

def test_reset_password_successfully_changes_password(client):
    token = "valid-reset-token"

    user_id = create_test_reset_token(
        client,
        "valid.reset@example.com",
        token,
        datetime.utcnow() + timedelta(minutes=10),
    )

    result = password_reset_module.reset_user_password(
        token,
        "NewPassword123",
    )

    assert result is True

    db = password_reset_module.SessionLocal()
    try:
        user = db.query(User).filter(
            User.id == user_id
        ).first()

        assert user is not None
        assert user.password_hash != "OldPassword123"

        reset_token_hash = hashlib.sha256(
            token.encode("utf-8")
        ).hexdigest()

        token_record = db.execute(
            text("""
                SELECT used_at
                FROM password_reset_tokens
                WHERE token_hash = :token_hash
            """),
            {"token_hash": reset_token_hash},
        ).mappings().first()

        assert token_record is not None
        assert token_record["used_at"] is not None
    finally:
        db.close()


def test_reset_password_token_cannot_be_reused(client):
    token = "single-use-reset-token"

    create_test_reset_token(
        client,
        "single.use@example.com",
        token,
        datetime.utcnow() + timedelta(minutes=10),
    )

    first_result = password_reset_module.reset_user_password(
        token,
        "NewPassword123",
    )

    second_result = password_reset_module.reset_user_password(
        token,
        "AnotherPassword123",
    )

    assert first_result is True
    assert second_result is False

    
def test_password_reset_email_is_composed_correctly(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "test@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-smtp-password")

    reset_url = (
        "http://testserver/reset-password"
        "?token=sample-reset-token"
    )

    with patch("app.password_reset.smtplib.SMTP") as smtp_mock:
        server = smtp_mock.return_value.__enter__.return_value

        send_password_reset_email(
            "student@example.com",
            reset_url,
        )

        smtp_mock.assert_called_once_with(
            "smtp.gmail.com",
            587,
        )
        server.starttls.assert_called_once()
        server.login.assert_called_once_with(
            "test@example.com",
            "test-smtp-password",
        )

        server.send_message.assert_called_once()

        message = server.send_message.call_args.args[0]

        assert message["To"] == "student@example.com"
        assert "Reset Your AI Study Planner Password" in message["Subject"]
        assert reset_url in message.get_content()
        assert "20 minutes" in message.get_content()


def test_password_reset_email_rejects_missing_smtp_settings(monkeypatch):
    monkeypatch.delenv("SMTP_EMAIL", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    with patch("app.password_reset.smtplib.SMTP") as smtp_mock:
        try:
            send_password_reset_email(
                "student@example.com",
                "http://testserver/reset-password?token=test-token",
            )
            assert False, "Expected missing SMTP settings to raise an error"
        except ValueError as exc:
            assert "SMTP email settings are missing" in str(exc)

        smtp_mock.assert_not_called()


def test_password_reset_email_propagates_smtp_failure(monkeypatch):
    monkeypatch.setenv("SMTP_EMAIL", "test@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "test-smtp-password")

    with patch("app.password_reset.smtplib.SMTP") as smtp_mock:
        server = smtp_mock.return_value.__enter__.return_value
        server.send_message.side_effect = OSError("Simulated SMTP failure")

        try:
            send_password_reset_email(
                "student@example.com",
                "http://testserver/reset-password?token=test-token",
            )
            assert False, "Expected SMTP failure to propagate"
        except OSError as exc:
            assert "Simulated SMTP failure" in str(exc)
