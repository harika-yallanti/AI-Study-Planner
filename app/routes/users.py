from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from pwdlib import PasswordHash

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse, UserLogin

import os

import logging
import firebase_admin
import secrets

from firebase_admin import auth as firebase_auth
from firebase_admin import credentials, initialize_app

import firebase_admin
router = APIRouter(
    prefix="/users",
    tags=["Users"]
)

logger = logging.getLogger(__name__)


# Firebase Admin initialization
from dotenv import load_dotenv

load_dotenv()

try:
    firebase_admin.get_app()
except ValueError:
    service_account_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")
    project_id = os.getenv("FIREBASE_PROJECT_ID")

    if not service_account_path or not project_id:
        raise RuntimeError(
            "FIREBASE_SERVICE_ACCOUNT_PATH and "
            "FIREBASE_PROJECT_ID must be configured in .env"
        )

    firebase_credential = credentials.Certificate(service_account_path)

    firebase_admin.initialize_app(
        firebase_credential,
        {"projectId": project_id}
    )

password_hash = PasswordHash.recommended()


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED
)
def register_user(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    # Check whether the email is already registered.
    existing_user = db.query(User).filter(
        User.email == user_data.email
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email is already registered"
        )

    # Hash the password before saving it.
    hashed_password = password_hash.hash(
        user_data.password
    )

    # Create a new student.
    new_user = User(
        name=user_data.name,
        email=user_data.email,
        password_hash=hashed_password
    )

    db.add(new_user)
    db.flush()
    db.refresh(new_user)

    return new_user


@router.post("/login")
def login_user(
    request: Request,
    login_data: UserLogin,
    db: Session = Depends(get_db)
):
    # Find the user using their email.
    user = db.query(User).filter(
        User.email == login_data.email
    ).first()

    # Check whether the user exists.
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Verify the entered password.
    if not password_hash.verify(
        login_data.password,
        user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password"
        )

    # Prevent deactivated accounts from logging in.
    if not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account has been deactivated. Contact the administrator."
        )

    # Clear any previous session data.
    request.session.clear()

    # Create a session for the logged-in user.
    request.session["user_id"] = user.id
    request.session["user_name"] = user.name
    request.session["user_email"] = user.email
    request.session["user_role"] = user.role

    return {
        "message": "Login successful",
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role
    }


@router.post("/google-login")
def google_login(
    request: Request,
    payload: dict = Body(...),
    db: Session = Depends(get_db)
):
    token = payload.get("id_token")

    if not token:
        raise HTTPException(
            status_code=400,
            detail="Firebase ID token is required."
        )

    try:
        decoded_token = firebase_auth.verify_id_token(token)
    except Exception:
        logger.exception("Firebase ID token verification failed")
        raise HTTPException(
            status_code=401,
            detail="Google sign-in verification failed. Check the server terminal."
        )

    email = decoded_token.get("email")
    name = decoded_token.get("name") or (
        email.split("@")[0] if email else "Student"
    )

    if not email or decoded_token.get("email_verified") is not True:
        raise HTTPException(
            status_code=401,
            detail="Please use a verified Google email address."
        )

    user = db.query(User).filter(User.email == email).first()

    if user and not user.is_active:
        raise HTTPException(
            status_code=403,
            detail="Your account has been deactivated. Contact the administrator."
        )

    if not user:
        user = User(
            name=name[:100],
            email=email,
            password_hash=password_hash.hash(secrets.token_urlsafe(32)),
            role="student",
            is_active=True
        )

        db.add(user)

        try:
            db.commit()
            db.refresh(user)
        except Exception:
            db.rollback()
            logger.exception("Failed to create Google sign-in user")
            raise HTTPException(
                status_code=500,
                detail="Unable to create your account. Please try again."
            )

    request.session.clear()
    request.session["user_id"] = user.id
    request.session["user_name"] = user.name
    request.session["user_email"] = user.email
    request.session["user_role"] = user.role

    return {
        "message": "Google login successful",
        "user_id": user.id,
        "name": user.name,
        "email": user.email,
        "role": user.role
    }


@router.post("/logout")
def logout_user(request: Request):

    # Remove the logged-in user's session.
    request.session.clear()

    return {
        "message": "Logout successful"
    }


def require_admin(request: Request):
    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Please log in first"
        )

    if request.session.get("user_role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin access required"
        )
