from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.database import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/subjects")
def subjects_page(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        subjects = db.execute(
            text("""
                SELECT id, subject_name
                FROM subjects
                WHERE user_id = :user_id
                ORDER BY subject_name
            """),
            {"user_id": user_id}
        ).fetchall()

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "subjects.html",
        {
            "request": request,
            "subjects": subjects,
            "user_role": request.session.get("user_role", "student"),
            "error": request.query_params.get("error"),
            "success": request.query_params.get("success")
        }
    )


@router.post("/subjects")
def add_subject(
    request: Request,
    subject_name: str = Form(...)
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    subject_name = subject_name.strip()

    if not subject_name:
        return RedirectResponse(
            url="/subjects?error=empty",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Check whether this subject already exists for this student.
        existing_subject = db.execute(
            text("""
                SELECT id
                FROM subjects
                WHERE user_id = :user_id
                AND LOWER(TRIM(subject_name)) = LOWER(:subject_name)
                LIMIT 1
            """),
            {
                "user_id": user_id,
                "subject_name": subject_name
            }
        ).fetchone()

        if existing_subject:
            return RedirectResponse(
                url="/subjects?error=duplicate",
                status_code=303
            )

        # Insert the subject only if it does not already exist.
        db.execute(
            text("""
                INSERT INTO subjects (user_id, subject_name)
                VALUES (:user_id, :subject_name)
            """),
            {
                "user_id": user_id,
                "subject_name": subject_name
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(
        url="/subjects?success=added",
        status_code=303
    )
