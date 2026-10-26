from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.database import SessionLocal

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/subjects")
def subjects_page(request: Request):

    # Check whether the student is logged in.
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Get subjects belonging to this student.
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
            "subjects": subjects
        }
    )


@router.post("/subjects")
def add_subject(
    request: Request,
    subject_name: str = Form(...)
):

    # Check whether the student is logged in.
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    subject_name = subject_name.strip()

    # Do not save an empty subject name.
    if not subject_name:
        return RedirectResponse(
            url="/subjects",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Save the subject for this student.
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
        url="/subjects",
        status_code=303
    )