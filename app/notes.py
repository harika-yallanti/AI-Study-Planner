from io import BytesIO

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.database import SessionLocal


notes_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@notes_router.get("/notes")
def notes_page(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

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

        notes = db.execute(
            text("""
                SELECT
                    notes.id,
                    notes.title,
                    notes.content,
                    notes.created_at,
                    subjects.subject_name,
                    topics.topic_name

                FROM notes

                LEFT JOIN subjects
                    ON notes.subject_id = subjects.id

                LEFT JOIN topics
                    ON notes.topic_id = topics.id

                WHERE notes.user_id = :user_id

                ORDER BY notes.updated_at DESC
            """),
            {"user_id": user_id}
        ).fetchall()

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "notes.html",
        {
            "subjects": subjects,
            "notes": notes
        }
    )


@notes_router.post("/notes/add")
def add_note(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    subject_id: int = Form(...)
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    title = title.strip()
    content = content.strip()

    if not title or not content:
        return RedirectResponse("/notes", status_code=303)

    db = SessionLocal()

    try:
        subject = db.execute(
            text("""
                SELECT id
                FROM subjects
                WHERE id = :subject_id
                  AND user_id = :user_id
            """),
            {
                "subject_id": subject_id,
                "user_id": user_id
            }
        ).fetchone()

        if not subject:
            return RedirectResponse("/notes", status_code=303)

        db.execute(
            text("""
                INSERT INTO notes (
                    user_id,
                    subject_id,
                    title,
                    content
                )
                VALUES (
                    :user_id,
                    :subject_id,
                    :title,
                    :content
                )
            """),
            {
                "user_id": user_id,
                "subject_id": subject_id,
                "title": title,
                "content": content
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse("/notes", status_code=303)


@notes_router.get("/notes/{note_id}/download")
def download_note(request: Request, note_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        note = db.execute(
            text("""
                SELECT title, content
                FROM notes
                WHERE id = :note_id
                  AND user_id = :user_id
            """),
            {
                "note_id": note_id,
                "user_id": user_id
            }
        ).fetchone()

    finally:
        db.close()

    if not note:
        return RedirectResponse("/notes", status_code=303)

    file_content = (
        f"{note.title}\n\n"
        f"{note.content}"
    )

    filename = "note.txt"

    return StreamingResponse(
        BytesIO(file_content.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="{filename}"'
        }
    )