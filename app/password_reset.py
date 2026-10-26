
import hashlib
import os
import secrets
import smtplib

from datetime import datetime, timedelta
from email.message import EmailMessage
from urllib.parse import quote

from dotenv import load_dotenv
from sqlalchemy import text

from app.database import SessionLocal
from app.models import User
from app.routes.users import password_hash

load_dotenv()


def send_password_reset_email(recipient: str, reset_url: str):
    sender = os.getenv("SMTP_EMAIL")
    password = os.getenv("SMTP_PASSWORD")

    if not sender or not password:
        raise ValueError("SMTP email settings are missing.")

    message = EmailMessage()
    message["Subject"] = "Reset Your AI Study Planner Password"
    message["From"] = sender
    message["To"] = recipient

    message.set_content(
        f"""Hello,

We received a request to reset your AI Study Planner password.

Use the following link to choose a new password:

{reset_url}

This link expires in 20 minutes and can only be used once.
If you did not request this, you can ignore this email.

AI Study Planner
"""
    )

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(message)


def create_password_reset(user: User, base_url: str):
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.utcnow() + timedelta(minutes=20)

    db = SessionLocal()

    try:
        db.execute(
            text("""
                UPDATE password_reset_tokens
                SET used_at = UTC_TIMESTAMP()
                WHERE user_id = :user_id
                  AND used_at IS NULL
            """),
            {"user_id": user.id}
        )

        db.execute(
            text("""
                INSERT INTO password_reset_tokens
                    (user_id, token_hash, expires_at)
                VALUES
                    (:user_id, :token_hash, :expires_at)
            """),
            {
                "user_id": user.id,
                "token_hash": token_hash,
                "expires_at": expires_at
            }
        )

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    reset_url = (
        f"{base_url.rstrip('/')}/reset-password"
        f"?token={quote(raw_token)}"
    )

    send_password_reset_email(user.email, reset_url)


def reset_user_password(raw_token: str, new_password: str):
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    db = SessionLocal()

    try:
        reset_record = db.execute(
            text("""
                SELECT id, user_id
                FROM password_reset_tokens
                WHERE token_hash = :token_hash
                  AND used_at IS NULL
                  AND expires_at > UTC_TIMESTAMP()
                FOR UPDATE
            """),
            {"token_hash": token_hash}
        ).mappings().first()

        if not reset_record:
            return False

        user = db.query(User).filter(
            User.id == reset_record["user_id"]
        ).first()

        if not user or not user.is_active:
            return False

        user.password_hash = password_hash.hash(new_password)

        db.execute(
            text("""
                UPDATE password_reset_tokens
                SET used_at = UTC_TIMESTAMP()
                WHERE user_id = :user_id
                  AND used_at IS NULL
            """),
            {"user_id": user.id}
        )

        db.commit()
        return True

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
