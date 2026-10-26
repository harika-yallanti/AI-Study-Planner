import os

from datetime import date, timedelta

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.database import SessionLocal

from app.routes.subjects import router as subjects_router
from app.routes.users import router as users_router
from app.routes.topics import topics_router
from app.routes.syllabus import syllabus_router
from app.routes.ai import ai_router
from app.routes.study_sessions import router as study_sessions_router

from app.reminders import (
    start_reminder_scheduler,
    stop_reminder_scheduler
)

from app.notes import notes_router
from app.resources import resources_router

import secrets

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from app.models import User
from app.password_reset import (
    create_password_reset,
    reset_user_password
)


app = FastAPI(title="AI Study Planner")

templates = Jinja2Templates(directory="app/templates")

# Add session support for logged-in users.
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv(
        "SESSION_SECRET",
        "dev-only-change-this-secret"
    ),
    same_site="lax",
    https_only=False
)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

app.include_router(users_router)
app.include_router(subjects_router)
app.include_router(topics_router)
app.include_router(syllabus_router)
app.include_router(ai_router)
app.include_router(study_sessions_router)
app.include_router(notes_router)
app.include_router(resources_router)

@app.get("/")
def home(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(
            url="/dashboard",
            status_code=303
        )

    return RedirectResponse(
        url="/login",
        status_code=303
    )

@app.on_event("startup")
def start_background_reminders():
    start_reminder_scheduler()


@app.on_event("shutdown")
def stop_background_reminders():
    stop_reminder_scheduler()

@app.get("/login")
def login_page(request: Request):

    # Redirect logged-in users to the dashboard.
    if request.session.get("user_id"):
        return RedirectResponse(
            url="/dashboard",
            status_code=303
        )

    return templates.TemplateResponse(
        request,
        "login.html",
        {"request": request}
    )


@app.post("/forgot-password")
def forgot_password(
    request: Request,
    email: str = Form(...)
):
    normalized_email = email.strip().lower()

    generic_message = (
        "If an eligible account exists for that email, "
        "a password-reset link will be sent."
    )

    db = SessionLocal()

    try:
        user = db.query(User).filter(
            User.email == normalized_email
        ).first()

        # Do not reveal whether an account exists.
        if not user or not user.is_active:
            return templates.TemplateResponse(
                request,
                "forgot_password.html",
                {
                    "request": request,
                    "message": generic_message,
                    "success": True
                }
            )

        # Google-only accounts should continue using Google sign-in.
        # Keep this condition if your User model has an auth-provider field.
        base_url = os.getenv(
            "APP_BASE_URL",
            str(request.base_url).rstrip("/")
        ).rstrip("/")

        try:
            # IMPORTANT: Pass the User object, not user_id/recipient.
            create_password_reset(
                user=user,
                base_url=base_url
            )

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Password-reset email could not be sent"
            )

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {
            "request": request,
            "message": generic_message,
            "success": True
        }
    )


@app.get("/forgot-password")
def forgot_password_page(request: Request):
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"request": request, "message": None, "success": False}
    )


@app.get("/reset-password")
def reset_password_page(request: Request, token: str = ""):
    if not token or len(token) > 200:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "request": request,
                "token": "",
                "invalid_link": True
            }
        )

    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {
            "request": request,
            "token": token,
            "invalid_link": False
        }
    )


@app.post("/reset-password")
def reset_password_submit(
    request: Request,
    token: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...)
):
    if len(token) > 200:
        raise HTTPException(status_code=400, detail="Invalid reset link.")

    if len(new_password) < 8 or len(new_password) > 128:
        raise HTTPException(
            status_code=400,
            detail="Password must contain between 8 and 128 characters."
        )

    if new_password != confirm_password:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "request": request,
                "token": token,
                "invalid_link": False,
                "error": "Passwords do not match."
            },
            status_code=400
        )

    try:
        success = reset_user_password(token, new_password)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Password reset failed"
        )
        raise HTTPException(
            status_code=500,
            detail="Unable to reset the password right now. Please try again."
        )

    if not success:
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "request": request,
                "token": "",
                "invalid_link": True
            },
            status_code=400
        )

    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {
            "request": request,
            "token": "",
            "invalid_link": False,
            "completed": True
        }
    )


@app.get("/register")
def register_page(request: Request):

    # Registration is now part of login.html.
    return RedirectResponse(
        url="/login",
        status_code=303
    )


@app.get("/dashboard")
def dashboard(request: Request):

    # Check whether the student is logged in.
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Count the student's subjects.
        total_subjects = db.execute(
            text("""
                SELECT COUNT(*)
                FROM subjects
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).scalar()

        # Count the student's topics.
        total_topics = db.execute(
            text("""
                SELECT COUNT(*)
                FROM topics
                JOIN subjects ON topics.subject_id = subjects.id
                WHERE subjects.user_id = :user_id
            """),
            {"user_id": user_id}
        ).scalar()

        # Count the student's exams.
        total_exams = db.execute(
            text("""
                SELECT COUNT(*)
                FROM exams
                JOIN subjects ON exams.subject_id = subjects.id
                WHERE subjects.user_id = :user_id
            """),
            {"user_id": user_id}
        ).scalar()

        # Get the student's saved subjects.
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
        "dashboard.html",
        {
            "request": request,
            "total_subjects": total_subjects,
            "total_topics": total_topics,
            "total_exams": total_exams,
            "subjects": subjects,
            "user_role": request.session.get("user_role", "student")
        }
    )


@app.get("/admin/users")
def admin_users(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        # Verify the current user is an active administrator.
        admin = db.execute(
            text("""
                SELECT role, is_active
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()

        if not admin or admin.role != "admin" or not admin.is_active:
            return RedirectResponse("/dashboard", status_code=303)

        # Get all registered users.
        users = db.execute(
            text("""
                SELECT id, name, email, role, is_active, created_at
                FROM users
                ORDER BY created_at DESC
            """)
        ).fetchall()

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "admin_users.html",
        {
            "request": request,
            "users": users
        }
    )


@app.post("/admin/users/{user_id}/toggle")
def toggle_user_status(request: Request, user_id: int):

    admin_id = request.session.get("user_id")

    if not admin_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        # Verify administrator permissions.
        admin = db.execute(
            text("""
                SELECT role, is_active
                FROM users
                WHERE id = :admin_id
            """),
            {"admin_id": admin_id}
        ).fetchone()

        if not admin or admin.role != "admin" or not admin.is_active:
            return RedirectResponse("/dashboard", status_code=303)

        # Find the selected student.
        user = db.execute(
            text("""
                SELECT id, role, is_active
                FROM users
                WHERE id = :user_id
            """),
            {"user_id": user_id}
        ).fetchone()

        # Only student accounts can be changed here.
        if user and user.role == "student":
            new_status = not bool(user.is_active)

            db.execute(
                text("""
                    UPDATE users
                    SET is_active = :new_status
                    WHERE id = :user_id
                """),
                {
                    "new_status": new_status,
                    "user_id": user_id
                }
            )

            db.commit()

    finally:
        db.close()

    return RedirectResponse("/admin/users", status_code=303)


@app.get("/study-progress")
def study_progress(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Get overall study statistics.
        study_stats = db.execute(
            text("""
                SELECT
                    COUNT(*) AS completed_sessions,
                    COALESCE(
                        SUM(
                            COALESCE(
                                duration_seconds,
                                duration_minutes * 60
                            )
                        ),
                        0
                    ) AS total_seconds
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NOT NULL
            """),
            {"user_id": user_id}
        ).first()

        # Get overall quiz performance.
        quiz_stats = db.execute(
            text("""
                SELECT
                    COUNT(*) AS quiz_attempts,
                    COALESCE(SUM(score), 0) AS total_score,
                    COALESCE(SUM(total_questions), 0)
                        AS total_questions
                FROM quiz_attempts
                WHERE user_id = :user_id
            """),
            {"user_id": user_id}
        ).first()

        # Get study time for each subject.
        subject_progress = db.execute(
            text("""
                SELECT
                    subjects.id,
                    subjects.subject_name,
                    COUNT(study_sessions.id) AS completed_sessions,
                    COALESCE(
                        SUM(
                            COALESCE(
                                study_sessions.duration_seconds,
                                study_sessions.duration_minutes * 60
                            )
                        ),
                        0
                    ) AS total_seconds
                FROM subjects
                LEFT JOIN topics
                    ON topics.subject_id = subjects.id
                LEFT JOIN study_sessions
                    ON study_sessions.topic_id = topics.id
                    AND study_sessions.user_id = :user_id
                    AND study_sessions.ended_at IS NOT NULL
                WHERE subjects.user_id = :user_id
                GROUP BY
                    subjects.id,
                    subjects.subject_name
                ORDER BY total_seconds DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        # Get recent completed study sessions.
        recent_sessions = db.execute(
            text("""
                SELECT
                    topics.topic_name,
                    subjects.subject_name,
                    study_sessions.started_at,
                    study_sessions.ended_at,
                    COALESCE(
                        study_sessions.duration_seconds,
                        study_sessions.duration_minutes * 60
                    ) AS duration_seconds
                FROM study_sessions
                JOIN topics
                    ON study_sessions.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE study_sessions.user_id = :user_id
                  AND study_sessions.ended_at IS NOT NULL
                ORDER BY study_sessions.ended_at DESC
                LIMIT 10
            """),
            {"user_id": user_id}
        ).fetchall()

        # Get today's completed study time.
        today = date.today()

        daily_stats = db.execute(
            text("""
                SELECT
                    COALESCE(
                        SUM(
                            COALESCE(
                                duration_seconds,
                                duration_minutes * 60
                            )
                        ),
                        0
                    ) AS today_seconds
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NOT NULL
                  AND DATE(ended_at) = :today
            """),
            {
                "user_id": user_id,
                "today": today
            }
        ).first()

        # Get all days on which the student completed a session.
        study_days = db.execute(
            text("""
                SELECT DISTINCT DATE(ended_at) AS study_date
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NOT NULL
                ORDER BY study_date DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        # Get study time for the last 7 days.
        weekly_sessions = db.execute(
            text("""
                SELECT
                    DATE(ended_at) AS study_date,
                    COALESCE(
                        SUM(
                            COALESCE(
                                duration_seconds,
                                duration_minutes * 60
                            )
                        ),
                        0
                    ) AS total_seconds
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NOT NULL
                  AND DATE(ended_at) >= :start_date
                  AND DATE(ended_at) <= :today
                GROUP BY DATE(ended_at)
                ORDER BY study_date
            """),
            {
                "user_id": user_id,
                "start_date": today - timedelta(days=6),
                "today": today
            }
        ).fetchall()

        # Get the last 7 quiz attempts.
        recent_quiz_attempts = db.execute(
            text("""
                SELECT
                    quiz_attempts.score,
                    quiz_attempts.total_questions,
                    quiz_attempts.attempted_at,
                    topics.topic_name,
                    subjects.subject_name
                FROM quiz_attempts
                JOIN topics
                    ON quiz_attempts.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE quiz_attempts.user_id = :user_id
                  AND quiz_attempts.total_questions > 0
                  AND subjects.user_id = :user_id
                ORDER BY
                    quiz_attempts.attempted_at DESC,
                    quiz_attempts.id DESC
                LIMIT 7
            """),
            {"user_id": user_id}
        ).fetchall()

        # Get quiz performance for each subject.
        subject_quiz_progress = db.execute(
            text("""
                SELECT
                    subjects.id,
                    subjects.subject_name,
                    COUNT(quiz_attempts.id) AS quiz_attempts,
                    COALESCE(SUM(quiz_attempts.score), 0) AS total_score,
                    COALESCE(
                        SUM(quiz_attempts.total_questions),
                        0
                    ) AS total_questions
                FROM subjects
                JOIN topics
                    ON topics.subject_id = subjects.id
                LEFT JOIN quiz_attempts
                    ON quiz_attempts.topic_id = topics.id
                    AND quiz_attempts.user_id = :user_id
                    AND quiz_attempts.total_questions > 0
                WHERE subjects.user_id = :user_id
                GROUP BY
                    subjects.id,
                    subjects.subject_name
                ORDER BY subjects.subject_name
            """),
            {"user_id": user_id}
        ).fetchall()

    finally:
        db.close()

    # Prepare quiz performance chart data.
    quiz_chart_labels = []
    quiz_chart_scores = []

    # Reverse the results so the chart shows oldest to newest.
    for attempt in reversed(recent_quiz_attempts):

        total_questions = int(attempt.total_questions or 0)
        score = float(attempt.score or 0)

        if total_questions > 0:
            quiz_percentage = round(
                score / total_questions * 100,
                1
            )
        else:
            quiz_percentage = 0.0

        quiz_chart_labels.append(
            attempt.attempted_at.strftime("%d %b %H:%M")
        )

        quiz_chart_scores.append(float(quiz_percentage))

    # Prepare subject-wise quiz performance.
    subject_quiz_data = []

    for subject in subject_quiz_progress:

        total_questions = int(subject.total_questions or 0)
        total_score = float(subject.total_score or 0)

        if total_questions > 0:
            percentage = round(
                total_score / total_questions * 100,
                1
            )
        else:
            percentage = 0.0

        subject_quiz_data.append({
            "id": subject.id,
            "subject_name": subject.subject_name,
            "quiz_attempts": int(subject.quiz_attempts or 0),
            "average_score": float(percentage)
        })

    # Prepare weekly study chart data.
    weekly_study_data = {
        row.study_date: float(
            round(
                float(row.total_seconds or 0) / 60,
                1
            )
        )
        for row in weekly_sessions
    }

    subject_quiz_labels = [
        subject["subject_name"]
        for subject in subject_quiz_data
        if subject["quiz_attempts"] > 0
    ]

    subject_quiz_scores = [
        float(subject["average_score"])
        for subject in subject_quiz_data
        if subject["quiz_attempts"] > 0
    ]

    weekly_chart_labels = []
    weekly_chart_minutes = []

    for day_offset in range(6, -1, -1):
        chart_date = today - timedelta(days=day_offset)

        weekly_chart_labels.append(
            chart_date.strftime("%a")
        )

        weekly_chart_minutes.append(
            float(weekly_study_data.get(chart_date, 0))
        )

    # Calculate current and longest study streaks.
    dates = [
        row.study_date
        for row in study_days
    ]

    current_streak = 0
    longest_streak = 0

    if dates:
        longest_streak = 1
        streak = 1

        # Calculate the longest streak.
        for i in range(1, len(dates)):
            difference = (
                dates[i - 1] - dates[i]
            ).days

            if difference == 1:
                streak += 1
            else:
                streak = 1

            longest_streak = max(
                longest_streak,
                streak
            )

        # Calculate the current streak.
        if today in dates:
            current_streak = 1
            check_date = today - timedelta(days=1)

        elif today - timedelta(days=1) in dates:
            current_streak = 1
            check_date = today - timedelta(days=2)

        else:
            check_date = None

        # Count consecutive study days.
        if check_date:
            while check_date in dates:
                current_streak += 1
                check_date -= timedelta(days=1)

    # Calculate total study time.
    total_seconds = int(
        study_stats.total_seconds or 0
    ) if study_stats else 0

    total_hours = total_seconds // 3600
    remaining_minutes = (total_seconds % 3600) // 60
    remaining_seconds = total_seconds % 60

    # Calculate quiz percentage.
    average_quiz_score = 0.0

    quiz_total_questions = int(
        quiz_stats.total_questions or 0
    ) if quiz_stats else 0

    quiz_total_score = float(
        quiz_stats.total_score or 0
    ) if quiz_stats else 0.0

    if quiz_total_questions > 0:
        average_quiz_score = round(
            quiz_total_score
            / quiz_total_questions
            * 100,
            1
        )

    quiz_attempt_count = int(
        quiz_stats.quiz_attempts or 0
    ) if quiz_stats else 0

    # Prepare subject progress bars.
    subject_progress_data = []

    for subject in subject_progress:
        subject_seconds = int(subject.total_seconds or 0)

        if total_seconds > 0:
            percentage = round(
                subject_seconds / total_seconds * 100,
                1
            )
        else:
            percentage = 0.0

        subject_progress_data.append({
            "id": subject.id,
            "subject_name": subject.subject_name,
            "completed_sessions": int(subject.completed_sessions or 0),
            "total_seconds": subject_seconds,
            "total_minutes": subject_seconds // 60,
            "percentage": float(percentage)
        })

    # Calculate the daily study goal.
    daily_goal_minutes = 120
    daily_goal_seconds = daily_goal_minutes * 60

    today_seconds = int(
        daily_stats.today_seconds or 0
    ) if daily_stats else 0

    today_hours = today_seconds // 3600
    today_minutes = (today_seconds % 3600) // 60
    today_remaining_seconds = today_seconds % 60

    daily_remaining_seconds = max(
        0,
        daily_goal_seconds - today_seconds
    )

    daily_remaining_minutes = (
        daily_remaining_seconds // 60
    )

    daily_progress = min(
        100,
        round(
            today_seconds / daily_goal_seconds * 100,
            1
        )
    )

    # Format recent session durations.
    recent_session_data = []

    for session in recent_sessions:
        seconds = int(session.duration_seconds or 0)

        if seconds < 60:
            duration_display = f"{seconds} sec"

        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60

            if remaining_seconds:
                duration_display = (
                    f"{minutes} min {remaining_seconds} sec"
                )
            else:
                duration_display = f"{minutes} min"

        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60

            duration_display = f"{hours} hr {minutes} min"

        recent_session_data.append({
            "topic_name": session.topic_name,
            "subject_name": session.subject_name,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
            "duration_seconds": seconds,
            "duration_display": duration_display
        })

    return templates.TemplateResponse(
        request,
        "study_progress.html",
        {
            "request": request,

            "completed_sessions": int(
                study_stats.completed_sessions or 0
            ) if study_stats else 0,

            "total_hours": total_hours,
            "remaining_minutes": remaining_minutes,
            "remaining_seconds": remaining_seconds,
            "total_seconds": total_seconds,

            "quiz_attempts": quiz_attempt_count,
            "average_quiz_score": float(average_quiz_score),

            "subject_progress": subject_progress_data,
            "recent_sessions": recent_session_data,

            "current_streak": current_streak,
            "longest_streak": longest_streak,
            "studied_today": today in dates,

            "daily_goal_minutes": daily_goal_minutes,
            "today_hours": today_hours,
            "today_minutes": today_minutes,
            "today_remaining_seconds": today_remaining_seconds,
            "daily_remaining_minutes": daily_remaining_minutes,
            "daily_progress": float(daily_progress),

            "weekly_chart_labels": weekly_chart_labels,
            "weekly_chart_minutes": weekly_chart_minutes,

            "quiz_chart_labels": quiz_chart_labels,
            "quiz_chart_scores": quiz_chart_scores,

            "subject_quiz_data": subject_quiz_data,
            "subject_quiz_labels": subject_quiz_labels,
            "subject_quiz_scores": subject_quiz_scores
        }
    )
