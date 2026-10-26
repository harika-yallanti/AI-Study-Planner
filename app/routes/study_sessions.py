
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from datetime import date, time

from app.database import SessionLocal


router = APIRouter()


@router.post("/study/start")
def start_study(
    request: Request,
    topic_id: int = Form(...)
):
    # Check whether the student is logged in.
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Check whether the topic belongs to this student.
        topic = db.execute(
            text("""
                SELECT topics.id
                FROM topics
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE topics.id = :topic_id
                  AND subjects.user_id = :user_id
            """),
            {
                "topic_id": topic_id,
                "user_id": user_id
            }
        ).fetchone()

        if not topic:
            return RedirectResponse(
                url="/study-plan",
                status_code=303
            )

        # Check whether the student already has an active session.
        active_session = db.execute(
            text("""
                SELECT id
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NULL
            """),
            {"user_id": user_id}
        ).fetchone()

        if active_session:
            return RedirectResponse(
                url="/study-plan",
                status_code=303
            )

        # Start a new study session.
        db.execute(
            text("""
                INSERT INTO study_sessions (user_id, topic_id)
                VALUES (:user_id, :topic_id)
            """),
            {
                "user_id": user_id,
                "topic_id": topic_id
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(
        url="/study-plan",
        status_code=303
    )

@router.post("/study/stop")
def stop_study(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Find the student's active study session.
        active_session = db.execute(
            text("""
                SELECT id
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NULL
                ORDER BY started_at DESC
                LIMIT 1
            """),
            {"user_id": user_id}
        ).fetchone()

        if not active_session:
            return RedirectResponse(
                url="/subjects",
                status_code=303
            )

        # Save the end time and calculate the exact duration.
        db.execute(
            text("""
                UPDATE study_sessions
                SET ended_at = CURRENT_TIMESTAMP,

                    duration_seconds = TIMESTAMPDIFF(
                        SECOND,
                        started_at,
                        CURRENT_TIMESTAMP
                    ),

                    duration_minutes = FLOOR(
                        TIMESTAMPDIFF(
                            SECOND,
                            started_at,
                            CURRENT_TIMESTAMP
                        ) / 60
                    )

                WHERE id = :session_id
                  AND user_id = :user_id
                  AND ended_at IS NULL
            """),
            {
                "session_id": active_session.id,
                "user_id": user_id
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(
        url="/study-plan",
        status_code=303
    )