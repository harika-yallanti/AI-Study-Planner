
import os
import uuid
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.database import SessionLocal


resources_router = APIRouter()

templates = Jinja2Templates(directory="app/templates")

UPLOAD_DIR = Path("app/static/uploads/resources")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 15 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf", ".ppt", ".pptx",
    ".doc", ".docx",
    ".txt", ".csv",
    ".jpg", ".jpeg", ".png"
}


# Check whether a subject belongs to the logged-in student
def subject_belongs_to_user(db, subject_id, user_id):
    return db.execute(
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
    ).first()


# Validate a website or YouTube URL
def valid_resource_url(url):
    parsed_url = urlparse(url.strip())

    return (
        parsed_url.scheme in {"http", "https"}
        and bool(parsed_url.netloc)
    )


# Save an uploaded file and enforce the 15 MB limit
def save_uploaded_resource(uploaded_file):
    if not uploaded_file or not uploaded_file.filename:
        raise ValueError("Please select a file to upload.")

    original_filename = Path(uploaded_file.filename).name
    extension = Path(original_filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("This file type is not allowed.")

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    saved_path = UPLOAD_DIR / stored_filename

    file_size = 0

    try:
        with open(saved_path, "wb") as output_file:
            while True:
                chunk = uploaded_file.file.read(1024 * 1024)

                if not chunk:
                    break

                file_size += len(chunk)

                if file_size > MAX_FILE_SIZE:
                    raise ValueError(
                        "File size must be 15 MB or less."
                    )

                output_file.write(chunk)

        return saved_path, original_filename

    except Exception:
        if saved_path.exists():
            saved_path.unlink()
        raise


# Safely remove a resource's stored file
def remove_resource_file(file_path):
    if not file_path:
        return

    try:
        path = Path(file_path).resolve()
        upload_directory = UPLOAD_DIR.resolve()

        if path.is_relative_to(upload_directory) and path.is_file():
            path.unlink()

    except OSError:
        # Database deletion/update has already been committed.
        # A file cleanup failure should not undo that database change.
        pass


# Show the Learning Resources page
@resources_router.get("/resources")
def resources_page(request: Request):

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
        ).mappings().all()

        resources = db.execute(
            text("""
                SELECT
                    resources.id,
                    resources.title,
                    resources.description,
                    resources.resource_type,
                    resources.resource_url,
                    resources.original_filename,
                    resources.created_at,
                    subjects.subject_name,
                    topics.topic_name

                FROM resources

                JOIN subjects
                    ON resources.subject_id = subjects.id

                LEFT JOIN topics
                    ON resources.topic_id = topics.id

                WHERE resources.user_id = :user_id

                ORDER BY resources.created_at DESC
            """),
            {"user_id": user_id}
        ).mappings().all()

        return templates.TemplateResponse(
            request,
            "resources.html",
            {
                "subjects": subjects,
                "resources": resources
            }
        )

    finally:
        db.close()


# Add a file or a website/video link
@resources_router.post("/resources/add")
def add_resource(
    request: Request,
    subject_id: int = Form(...),
    topic_id: int = Form(None),
    title: str = Form(...),
    description: str = Form(""),
    resource_type: str = Form(...),
    resource_url: str = Form(""),
    uploaded_file: UploadFile = File(None)
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    title = title.strip()
    description = description.strip()

    if not title:
        return HTMLResponse(
            "Resource title is required.",
            status_code=400
        )

    if resource_type not in {"file", "link"}:
        return HTMLResponse(
            "Invalid resource type.",
            status_code=400
        )

    db = SessionLocal()
    saved_path = None

    try:
        if not subject_belongs_to_user(db, subject_id, user_id):
            return HTMLResponse(
                "Invalid subject selected.",
                status_code=400
            )

        if topic_id is not None:
            topic = db.execute(
                text("""
                    SELECT id
                    FROM topics
                    WHERE id = :topic_id
                    AND subject_id = :subject_id
                """),
                {
                    "topic_id": topic_id,
                    "subject_id": subject_id
                }
            ).first()

            if not topic:
                return HTMLResponse(
                    "Invalid topic selected.",
                    status_code=400
                )

        if resource_type == "link":
            resource_url = resource_url.strip()

            if not valid_resource_url(resource_url):
                return HTMLResponse(
                    "Please enter a valid website or video URL.",
                    status_code=400
                )

            original_filename = None

        else:
            try:
                saved_path, original_filename = save_uploaded_resource(
                    uploaded_file
                )
            except ValueError as error:
                return HTMLResponse(str(error), status_code=400)

            resource_url = None

        db.execute(
            text("""
                INSERT INTO resources (
                    user_id,
                    subject_id,
                    topic_id,
                    title,
                    description,
                    resource_type,
                    resource_url,
                    file_path,
                    original_filename
                )
                VALUES (
                    :user_id,
                    :subject_id,
                    :topic_id,
                    :title,
                    :description,
                    :resource_type,
                    :resource_url,
                    :file_path,
                    :original_filename
                )
            """),
            {
                "user_id": user_id,
                "subject_id": subject_id,
                "topic_id": topic_id,
                "title": title,
                "description": description,
                "resource_type": resource_type,
                "resource_url": resource_url,
                "file_path": str(saved_path) if saved_path else None,
                "original_filename": original_filename
            }
        )

        db.commit()

        return RedirectResponse("/resources", status_code=303)

    except Exception:
        db.rollback()

        if saved_path and saved_path.exists():
            saved_path.unlink()

        raise

    finally:
        db.close()


# Show the Edit Resource page
@resources_router.get("/resources/{resource_id}/edit")
def edit_resource_page(
    request: Request,
    resource_id: int
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        resource = db.execute(
            text("""
                SELECT
                    id,
                    subject_id,
                    title,
                    description,
                    resource_type,
                    resource_url,
                    original_filename

                FROM resources

                WHERE id = :resource_id
                AND user_id = :user_id
            """),
            {
                "resource_id": resource_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not resource:
            return HTMLResponse(
                "Resource not found.",
                status_code=404
            )

        subjects = db.execute(
            text("""
                SELECT id, subject_name
                FROM subjects
                WHERE user_id = :user_id
                ORDER BY subject_name
            """),
            {"user_id": user_id}
        ).mappings().all()

        return templates.TemplateResponse(
            request,
            "resource_edit.html",
            {
                "resource": resource,
                "subjects": subjects
            }
        )

    finally:
        db.close()


# Save changes to a resource
@resources_router.post("/resources/{resource_id}/edit")
def update_resource(
    request: Request,
    resource_id: int,
    subject_id: int = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    resource_url: str = Form(""),
    uploaded_file: UploadFile = File(None)
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    title = title.strip()
    description = description.strip()

    if not title:
        return HTMLResponse(
            "Resource title is required.",
            status_code=400
        )

    db = SessionLocal()
    new_file_path = None
    old_file_path = None

    try:
        resource = db.execute(
            text("""
                SELECT
                    id,
                    resource_type,
                    file_path

                FROM resources

                WHERE id = :resource_id
                AND user_id = :user_id
            """),
            {
                "resource_id": resource_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not resource:
            return HTMLResponse(
                "Resource not found.",
                status_code=404
            )

        if not subject_belongs_to_user(db, subject_id, user_id):
            return HTMLResponse(
                "Invalid subject selected.",
                status_code=400
            )

        resource_type = resource["resource_type"]

        # Update a website or video link
        if resource_type == "link":

            resource_url = resource_url.strip()

            if not valid_resource_url(resource_url):
                return HTMLResponse(
                    "Please enter a valid website or video URL.",
                    status_code=400
                )

            db.execute(
                text("""
                    UPDATE resources
                    SET
                        subject_id = :subject_id,
                        title = :title,
                        description = :description,
                        resource_url = :resource_url

                    WHERE id = :resource_id
                    AND user_id = :user_id
                """),
                {
                    "subject_id": subject_id,
                    "title": title,
                    "description": description,
                    "resource_url": resource_url,
                    "resource_id": resource_id,
                    "user_id": user_id
                }
            )

        # Update an uploaded file resource
        else:

            old_file_path = resource["file_path"]

            if uploaded_file and uploaded_file.filename:

                try:
                    new_file_path, original_filename = (
                        save_uploaded_resource(uploaded_file)
                    )
                except ValueError as error:
                    return HTMLResponse(str(error), status_code=400)

                db.execute(
                    text("""
                        UPDATE resources
                        SET
                            subject_id = :subject_id,
                            title = :title,
                            description = :description,
                            file_path = :file_path,
                            original_filename = :original_filename

                        WHERE id = :resource_id
                        AND user_id = :user_id
                    """),
                    {
                        "subject_id": subject_id,
                        "title": title,
                        "description": description,
                        "file_path": str(new_file_path),
                        "original_filename": original_filename,
                        "resource_id": resource_id,
                        "user_id": user_id
                    }
                )

            else:
                db.execute(
                    text("""
                        UPDATE resources
                        SET
                            subject_id = :subject_id,
                            topic_id = NULL,
                            title = :title,
                            description = :description

                        WHERE id = :resource_id
                        AND user_id = :user_id
                    """),
                    {
                        "subject_id": subject_id,
                        "title": title,
                        "description": description,
                        "resource_id": resource_id,
                        "user_id": user_id
                    }
                )

        db.commit()

        # Remove the old file only after database changes succeed
        if new_file_path and old_file_path:
            remove_resource_file(old_file_path)

        return RedirectResponse("/resources", status_code=303)

    except Exception:
        db.rollback()

        if new_file_path and new_file_path.exists():
            new_file_path.unlink()

        raise

    finally:
        db.close()


# Delete a resource
@resources_router.post("/resources/{resource_id}/delete")
def delete_resource(
    request: Request,
    resource_id: int
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        resource = db.execute(
            text("""
                SELECT file_path
                FROM resources

                WHERE id = :resource_id
                AND user_id = :user_id
            """),
            {
                "resource_id": resource_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not resource:
            return HTMLResponse(
                "Resource not found.",
                status_code=404
            )

        file_path = resource["file_path"]

        db.execute(
            text("""
                DELETE FROM resources

                WHERE id = :resource_id
                AND user_id = :user_id
            """),
            {
                "resource_id": resource_id,
                "user_id": user_id
            }
        )

        db.commit()

        # Delete the physical file after the database commit
        remove_resource_file(file_path)

        return RedirectResponse("/resources", status_code=303)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# Download an uploaded resource
@resources_router.get("/resources/{resource_id}/download")
def download_resource(
    request: Request,
    resource_id: int
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        resource = db.execute(
            text("""
                SELECT
                    file_path,
                    original_filename

                FROM resources

                WHERE id = :resource_id
                AND user_id = :user_id
                AND resource_type = 'file'
            """),
            {
                "resource_id": resource_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not resource:
            return HTMLResponse(
                "Resource not found.",
                status_code=404
            )

        file_path = Path(resource["file_path"]).resolve()
        upload_directory = UPLOAD_DIR.resolve()

        if not file_path.is_relative_to(upload_directory):
            return HTMLResponse(
                "Invalid file location.",
                status_code=400
            )

        if not file_path.is_file():
            return HTMLResponse(
                "The uploaded file is missing.",
                status_code=404
            )

        return FileResponse(
            path=str(file_path),
            filename=resource["original_filename"],
            media_type="application/octet-stream"
        )

    finally:
        db.close()
