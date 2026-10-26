
import os
import uuid

from pathlib import Path

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from pypdf import PdfReader
from app.database import SessionLocal


syllabus_router = APIRouter()

UPLOAD_DIR = Path("uploads/syllabus")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@syllabus_router.post("/syllabus/upload")
async def upload_syllabus(
    request: Request,
    subject_id: int = Form(...),
    syllabus_file: UploadFile = File(...)
):
    # Check whether the student is logged in.
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Only accept PDF files.
    original_name = syllabus_file.filename or ""

    if Path(original_name).suffix.lower() != ".pdf":
        return RedirectResponse(
            url="/subjects",
            status_code=303
        )

    # Check that the subject belongs to this student.
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
        ).first()

        if not subject:
            return RedirectResponse(
                url="/subjects",
                status_code=303
            )

        # Read the uploaded PDF and check its size.
        file_content = await syllabus_file.read()

        if not file_content or len(file_content) > MAX_FILE_SIZE:
            return RedirectResponse(
                url="/subjects",
                status_code=303
            )

        # Check the PDF file signature.
        if not file_content.startswith(b"%PDF-"):
            return RedirectResponse(
                url="/subjects",
                status_code=303
            )

        # Create a unique filename to avoid overwriting files.
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

        saved_name = f"{uuid.uuid4().hex}.pdf"
        file_path = UPLOAD_DIR / saved_name

        # Extract text from the PDF.
        try:
            import io

            reader = PdfReader(io.BytesIO(file_content))

            if reader.is_encrypted:
                return RedirectResponse(
                    url="/subjects",
                    status_code=303
                )

            extracted_text = "\n".join(
                page.extract_text() or ""
                for page in reader.pages
            ).strip()

        except Exception:
            return RedirectResponse(
                url="/subjects",
                status_code=303
            )

        # Save the PDF to the private upload folder.
        with open(file_path, "wb") as pdf:
            pdf.write(file_content)

        # Save the PDF details and extracted text.
        db.execute(
            text("""
                INSERT INTO syllabi (
                    subject_id,
                    file_name,
                    file_path,
                    extracted_text,
                    processing_status
            )
            VALUES (
                :subject_id,
                :file_name,
                :file_path,
                :extracted_text,
                :processing_status
            )
            """),
            {
                "subject_id": subject_id,
                "file_name": os.path.basename(original_name),
                "file_path": str(file_path),
                "extracted_text": extracted_text,
                "processing_status": (
                    "extracted" if extracted_text else "needs_ocr"
                )
            }
        )

        db.commit()

    except Exception:
        db.rollback()

        # Remove the file if the database save fails.
        if "file_path" in locals() and file_path.exists():
            file_path.unlink()

        raise

    finally:
        db.close()
        await syllabus_file.close()

    return RedirectResponse(
        url="/subjects",
        status_code=303
    )
