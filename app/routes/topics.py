
from datetime import date, time, datetime, timedelta

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.database import SessionLocal


templates = Jinja2Templates(directory="app/templates")
topics_router = APIRouter()


@topics_router.post("/study/generate-timetable")
def generate_timetable(
    request: Request,
    planned_date: date = Form(...),
    start_time: time = Form(...),
    available_minutes: int = Form(...)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if available_minutes < 15 or available_minutes > 600:
        return RedirectResponse(url="/study-plan", status_code=303)

    db = SessionLocal()

    try:
        topics = db.execute(
            text("""
                SELECT
                    topics.id,
                    topics.topic_name,
                    topics.estimated_hours,
                    subjects.subject_name,

                    COALESCE(topics.difficulty, 3)
                    * COALESCE(topics.importance, 3)
                    AS base_priority_score,

                    (
                        SELECT MIN(exams.exam_date)
                        FROM exams
                        JOIN subjects exam_subjects
                            ON exams.subject_id = exam_subjects.id
                        WHERE exam_subjects.user_id = :user_id
                          AND exam_subjects.id = subjects.id
                          AND exams.exam_date >= :planned_date
                    ) AS next_exam_date,

                    (
                        SELECT
                            ROUND(
                                AVG(
                                    quiz_attempts.score
                                    / NULLIF(quiz_attempts.total_questions, 0)
                                ) * 100,
                                2
                            )
                        FROM quiz_attempts
                        WHERE quiz_attempts.topic_id = topics.id
                          AND quiz_attempts.user_id = :user_id
                          AND quiz_attempts.total_questions > 0
                    ) AS quiz_percentage

                FROM topics

                JOIN subjects
                    ON topics.subject_id = subjects.id

                WHERE subjects.user_id = :user_id

                AND NOT EXISTS (
                    SELECT 1
                    FROM planned_study_sessions
                    WHERE planned_study_sessions.topic_id = topics.id
                      AND planned_study_sessions.user_id = :user_id
                      AND planned_study_sessions.planned_date = :planned_date
                      AND planned_study_sessions.status = 'planned'
                )
            """),
            {
                "user_id": user_id,
                "planned_date": planned_date
            }
        ).fetchall()

        if not topics:
            return RedirectResponse(url="/study-plan", status_code=303)

        prioritized_topics = []

        for topic in topics:
            base_priority = topic.base_priority_score
            quiz_percentage = topic.quiz_percentage
            exam_date = topic.next_exam_date

            quiz_adjustment = 0

            if quiz_percentage is not None:
                if quiz_percentage < 60:
                    quiz_adjustment = base_priority * 0.50
                elif quiz_percentage < 80:
                    quiz_adjustment = base_priority * 0.20
                else:
                    quiz_adjustment = -base_priority * 0.20

            exam_adjustment = 0

            if exam_date is not None:
                days_until_exam = (exam_date - planned_date).days

                if days_until_exam <= 3:
                    exam_adjustment = 100
                elif days_until_exam <= 7:
                    exam_adjustment = 60
                elif days_until_exam <= 14:
                    exam_adjustment = 30

            timetable_priority = (
                base_priority
                + quiz_adjustment
                + exam_adjustment
            )

            prioritized_topics.append({
                "id": topic.id,
                "topic_name": topic.topic_name,
                "estimated_hours": topic.estimated_hours,
                "subject_name": topic.subject_name,
                "base_priority_score": base_priority,
                "quiz_percentage": quiz_percentage,
                "next_exam_date": exam_date,
                "timetable_priority": timetable_priority
            })

        prioritized_topics.sort(
            key=lambda topic: topic["timetable_priority"],
            reverse=True
        )

        remaining_minutes = available_minutes

        current_time = datetime.combine(
            planned_date,
            start_time
        )

        for topic in prioritized_topics:
            if remaining_minutes < 15:
                break

            session_minutes = min(60, remaining_minutes)

            db.execute(
                text("""
                    INSERT INTO planned_study_sessions (
                        user_id,
                        topic_id,
                        planned_date,
                        planned_time,
                        planned_minutes,
                        status,
                        reminder_sent
                    )
                    VALUES (
                        :user_id,
                        :topic_id,
                        :planned_date,
                        :planned_time,
                        :planned_minutes,
                        'planned',
                        0
                    )
                """),
                {
                    "user_id": user_id,
                    "topic_id": topic["id"],
                    "planned_date": planned_date,
                    "planned_time": current_time.time(),
                    "planned_minutes": session_minutes
                }
            )

            current_time += timedelta(minutes=session_minutes + 10)
            remaining_minutes -= session_minutes + 10

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(url="/study-plan", status_code=303)

@topics_router.post("/study/delete-session")
def delete_study_session(
    request: Request,
    planned_session_id: int = Form(...)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        session = db.execute(
            text("""
                SELECT id, status
                FROM planned_study_sessions
                WHERE id = :session_id
                  AND user_id = :user_id
            """),
            {
                "session_id": planned_session_id,
                "user_id": user_id
            }
        ).fetchone()

        if not session:
            request.session["schedule_message"] = (
                "Study session not found."
            )
            return RedirectResponse(
                url="/study-plan",
                status_code=303
            )

        if session.status not in ("missed", "planned", "completed"):
            request.session["schedule_message"] = (
                "This study session cannot be deleted."
            )
            return RedirectResponse(
                url="/study-plan",
                status_code=303
            )

        db.execute(
            text("""
                DELETE FROM planned_study_sessions
                WHERE id = :session_id
                  AND user_id = :user_id
            """),
            {
                "session_id": planned_session_id,
                "user_id": user_id
            }
        )

        db.commit()

        request.session["schedule_message"] = (
            "Study session deleted successfully."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(
        url="/study-plan",
        status_code=303
    )

@topics_router.post("/study/reschedule")
def reschedule_study(
    request: Request,
    planned_session_id: int = Form(...),
    planned_date: date = Form(...),
    planned_time: time = Form(...),
    planned_minutes: int = Form(60)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if planned_minutes < 15 or planned_minutes > 600:
        request.session["schedule_message"] = (
            "Study duration must be between 15 and 600 minutes."
        )
        return RedirectResponse(url="/study-plan", status_code=303)

    db = SessionLocal()

    try:
        # Check that this missed session belongs to the logged-in student.
        missed_session = db.execute(
            text("""
                SELECT planned_study_sessions.id
                FROM planned_study_sessions
                JOIN topics
                    ON planned_study_sessions.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE planned_study_sessions.id = :session_id
                  AND planned_study_sessions.user_id = :user_id
                  AND subjects.user_id = :user_id
                  AND planned_study_sessions.status = 'missed'
            """),
            {
                "session_id": planned_session_id,
                "user_id": user_id
            }
        ).fetchone()

        if not missed_session:
            request.session["schedule_message"] = (
                "This missed study session could not be found."
            )
            return RedirectResponse(url="/study-plan", status_code=303)

        # Check whether the new time overlaps another planned session.
        existing_sessions = db.execute(
            text("""
                SELECT id, planned_time, planned_minutes
                FROM planned_study_sessions
                WHERE user_id = :user_id
                  AND planned_date = :planned_date
                  AND status = 'planned'
                  AND id != :session_id
            """),
            {
                "user_id": user_id,
                "planned_date": planned_date,
                "session_id": planned_session_id
            }
        ).fetchall()

        new_start = datetime.combine(planned_date, planned_time)
        new_end = new_start + timedelta(minutes=planned_minutes)

        for session in existing_sessions:

            session_time = session.planned_time

            # MySQL TIME values may be returned as timedelta.
            if isinstance(session_time, timedelta):
                total_seconds = int(session_time.total_seconds())

                hours = (total_seconds // 3600) % 24
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60

                session_time = time(hours, minutes, seconds)

            existing_start = datetime.combine(
                planned_date,
                session_time
            )

            existing_end = existing_start + timedelta(
                minutes=session.planned_minutes
            )

            # The sessions overlap if either one starts
            # before the other one finishes.
            if new_start < existing_end and new_end > existing_start:

                request.session["schedule_message"] = (
                    f"Cannot reschedule this session to "
                    f"{planned_time.strftime('%I:%M %p')}. "
                    f"Another study session is already scheduled "
                    f"from {existing_start.strftime('%I:%M %p')} "
                    f"to {existing_end.strftime('%I:%M %p')} "
                    f"on {planned_date.strftime('%d %b %Y')}. "
                    f"Please choose another time."
                )

                return RedirectResponse(
                    url="/study-plan",
                    status_code=303
                )

        # No conflict: update the missed session.
        db.execute(
            text("""
                UPDATE planned_study_sessions
                SET planned_date = :planned_date,
                    planned_time = :planned_time,
                    planned_minutes = :planned_minutes,
                    status = 'planned',
                    reminder_sent = 0
                WHERE id = :session_id
                  AND user_id = :user_id
                  AND status = 'missed'
            """),
            {
                "planned_date": planned_date,
                "planned_time": planned_time,
                "planned_minutes": planned_minutes,
                "session_id": planned_session_id,
                "user_id": user_id
            }
        )

        db.commit()

        request.session["schedule_message"] = (
            "Study session rescheduled successfully!"
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(url="/study-plan", status_code=303)

@topics_router.post("/exams/add")
def add_exam(
    request: Request,
    subject_id: int = Form(...),
    exam_name: str = Form(...),
    exam_date: date = Form(...)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    exam_name = exam_name.strip()

    if not exam_name:
        return RedirectResponse(url="/study-plan#exams", status_code=303)

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
            return RedirectResponse(url="/exams", status_code=303)

        db.execute(
            text("""
                INSERT INTO exams (
                    subject_id,
                    exam_name,
                    exam_date
                )
                VALUES (
                    :subject_id,
                    :exam_name,
                    :exam_date
                )
            """),
            {
                "subject_id": subject_id,
                "exam_name": exam_name,
                "exam_date": exam_date
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(url="/exams", status_code=303)

@topics_router.get("/exams")
def exams_page(request: Request):
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

        exams = db.execute(
            text("""
                SELECT
                    exams.id,
                    exams.subject_id,
                    exams.exam_name,
                    exams.exam_date,
                    subjects.subject_name
                FROM exams
                JOIN subjects
                    ON exams.subject_id = subjects.id
                WHERE subjects.user_id = :user_id
                ORDER BY exams.exam_date ASC
            """),
            {"user_id": user_id}
        ).fetchall()

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "exams.html",
        {
            "subjects": subjects,
            "exams": exams,
            "today": date.today()
        }
    )

@topics_router.get("/exams/{exam_id}/prepare")
def prepare_exam_page(request: Request, exam_id: int):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    exams.id,
                    exams.exam_name,
                    exams.exam_date,
                    exams.subject_id,
                    subjects.subject_name
                FROM exams
                JOIN subjects
                    ON exams.subject_id = subjects.id
                WHERE exams.id = :exam_id
                  AND subjects.user_id = :user_id
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).fetchone()

        if not exam:
            return RedirectResponse(url="/exams", status_code=303)

        topics = db.execute(
            text("""
                SELECT
                    id,
                    topic_name,
                    difficulty,
                    importance,
                    estimated_hours
                FROM topics
                WHERE subject_id = :subject_id
                ORDER BY importance DESC, difficulty DESC
            """),
            {
                "subject_id": exam.subject_id
            }
        ).fetchall()

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "exam_prepare.html",
        {
            "exam": exam,
            "topics": topics,
            "today": date.today()
        }
    )

@topics_router.post("/exams/{exam_id}/prepare/generate")
def generate_exam_study_plan(
    request: Request,
    exam_id: int,
    study_start_date: date = Form(...),
    start_time: time = Form(...),
    daily_minutes: int = Form(...)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    # Validate daily study time.
    if daily_minutes < 15 or daily_minutes > 600:
        request.session["schedule_message"] = (
            "Study time must be between 15 and 600 minutes per day."
        )
        return RedirectResponse(
            url=f"/exams/{exam_id}/prepare",
            status_code=303
        )

    db = SessionLocal()

    try:
        # Check whether this exam belongs to the logged-in student.
        exam = db.execute(
            text("""
                SELECT
                    exams.id,
                    exams.exam_name,
                    exams.exam_date,
                    exams.subject_id
                FROM exams
                JOIN subjects
                    ON exams.subject_id = subjects.id
                WHERE exams.id = :exam_id
                  AND subjects.user_id = :user_id
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).fetchone()

        if not exam:
            return RedirectResponse(
                url="/exams",
                status_code=303
            )

        today = date.today()

        # Preparation cannot start in the past or after the exam.
        if study_start_date < today:
            request.session["schedule_message"] = (
                "Preparation start date cannot be in the past."
            )
            return RedirectResponse(
                url=f"/exams/{exam_id}/prepare",
                status_code=303
            )

        if study_start_date > exam.exam_date:
            request.session["schedule_message"] = (
                "Preparation start date cannot be after the exam date."
            )
            return RedirectResponse(
                url=f"/exams/{exam_id}/prepare",
                status_code=303
            )

        # Get the topics belonging to this exam's subject.
        topics = db.execute(
            text("""
                SELECT
                    topics.id,
                    topics.topic_name,
                    COALESCE(topics.estimated_hours, 1)
                        AS estimated_hours,

                    COALESCE(topics.difficulty, 3)
                    * COALESCE(topics.importance, 3)
                    AS base_priority_score,

                    (
                        SELECT
                            ROUND(
                                AVG(
                                    quiz_attempts.score
                                    / NULLIF(
                                        quiz_attempts.total_questions,
                                        0
                                    )
                                ) * 100,
                                2
                            )
                        FROM quiz_attempts
                        WHERE quiz_attempts.topic_id = topics.id
                          AND quiz_attempts.user_id = :user_id
                          AND quiz_attempts.total_questions > 0
                    ) AS quiz_percentage

                FROM topics

                WHERE topics.subject_id = :subject_id

                ORDER BY
                    topics.importance DESC,
                    topics.difficulty DESC
            """),
            {
                "subject_id": exam.subject_id,
                "user_id": user_id
            }
        ).fetchall()

        if not topics:
            request.session["schedule_message"] = (
                "No topics are available for this exam subject."
            )
            return RedirectResponse(
                url=f"/exams/{exam_id}/prepare",
                status_code=303
            )

        # Calculate the priority of each topic.
        prioritized_topics = []

        for topic in topics:

            base_priority = topic.base_priority_score
            quiz_percentage = topic.quiz_percentage

            quiz_adjustment = 0

            if quiz_percentage is not None:

                if quiz_percentage < 60:
                    quiz_adjustment = base_priority * 0.50

                elif quiz_percentage < 80:
                    quiz_adjustment = base_priority * 0.20

                else:
                    quiz_adjustment = -base_priority * 0.20

            prioritized_topics.append({
                "id": topic.id,
                "topic_name": topic.topic_name,
                "estimated_hours": topic.estimated_hours,
                "priority": base_priority + quiz_adjustment
            })

        prioritized_topics.sort(
            key=lambda topic: topic["priority"],
            reverse=True
        )

        # Build the timetable.
        # Schedule study sessions up to the day before the exam.
        current_date = study_start_date
        last_study_date = exam.exam_date - timedelta(days=1)

        if last_study_date < study_start_date:
            last_study_date = study_start_date

        sessions_created = 0

        for topic in prioritized_topics:

            # Convert the estimated topic hours into minutes.
            remaining_topic_minutes = max(
                15,
                int(topic["estimated_hours"] * 60)
            )

            while remaining_topic_minutes > 0:

                # Stop if there are no preparation days left.
                if current_date > last_study_date:
                    break

                # Start a new study day.
                remaining_daily_minutes = daily_minutes

                current_time = datetime.combine(
                    current_date,
                    start_time
                )

                while (
                    remaining_topic_minutes > 0
                    and remaining_daily_minutes >= 15
                ):

                    session_minutes = min(
                        60,
                        remaining_topic_minutes,
                        remaining_daily_minutes
                    )

                    # Save the study session.
                    db.execute(
                        text("""
                            INSERT INTO planned_study_sessions (
                                user_id,
                                topic_id,
                                planned_date,
                                planned_time,
                                planned_minutes,
                                status,
                                reminder_sent
                            )
                            VALUES (
                                :user_id,
                                :topic_id,
                                :planned_date,
                                :planned_time,
                                :planned_minutes,
                                'planned',
                                0
                            )
                        """),
                        {
                            "user_id": user_id,
                            "topic_id": topic["id"],
                            "planned_date": current_date,
                            "planned_time": current_time.time(),
                            "planned_minutes": session_minutes
                        }
                    )

                    sessions_created += 1

                    remaining_topic_minutes -= session_minutes
                    remaining_daily_minutes -= session_minutes

                    # Add a 10-minute break between sessions.
                    current_time += timedelta(
                        minutes=session_minutes + 10
                    )

                # Move to the next preparation day.
                current_date += timedelta(days=1)

        if sessions_created == 0:
            request.session["schedule_message"] = (
                "No study sessions could be generated."
            )
            return RedirectResponse(
                url=f"/exams/{exam_id}/prepare",
                status_code=303
            )

        db.commit()

        request.session["schedule_message"] = (
            f"Exam study plan generated successfully! "
            f"{sessions_created} study sessions created."
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(
        url="/study-plan",
        status_code=303
    )

@topics_router.get("/study-plan")
def study_plan(request: Request):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        syllabi = db.execute(
            text("""
                SELECT
                    syllabi.id,
                    syllabi.file_name,
                    syllabi.subject_id,
                    subjects.subject_name
                FROM syllabi
                JOIN subjects
                    ON syllabi.subject_id = subjects.id
                WHERE subjects.user_id = :user_id
                ORDER BY syllabi.uploaded_at DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        subjects = db.execute(
            text("""
                SELECT id, subject_name
                FROM subjects
                WHERE user_id = :user_id
                ORDER BY subject_name
            """),
            {"user_id": user_id}
        ).fetchall()

        topics = db.execute(
            text("""
                SELECT
                    topics.id,
                    topics.topic_name,
                    topics.difficulty,
                    topics.importance,
                    topics.estimated_hours,
                    subjects.subject_name,

                    COALESCE(
                        (
                            SELECT SUM(study_sessions.duration_minutes)
                            FROM study_sessions
                            WHERE study_sessions.topic_id = topics.id
                              AND study_sessions.ended_at IS NOT NULL
                        ),
                        0
                    ) AS total_study_minutes,

                    (
                        COALESCE(topics.difficulty, 3)
                        * COALESCE(topics.importance, 3)
                    ) AS base_priority_score,

                    (
                        SELECT
                            ROUND(
                                AVG(
                                    quiz_attempts.score
                                    / NULLIF(quiz_attempts.total_questions, 0)
                                ) * 100,
                                2
                            )
                        FROM quiz_attempts
                        WHERE quiz_attempts.topic_id = topics.id
                          AND quiz_attempts.user_id = :user_id
                          AND quiz_attempts.total_questions > 0
                    ) AS quiz_percentage,

                    (
                        SELECT COUNT(*)
                        FROM quiz_attempts
                        WHERE quiz_attempts.topic_id = topics.id
                          AND quiz_attempts.user_id = :user_id
                          AND quiz_attempts.total_questions > 0
                    ) AS quiz_attempt_count

                FROM topics

                JOIN subjects
                    ON topics.subject_id = subjects.id

                WHERE subjects.user_id = :user_id
            """),
            {"user_id": user_id}
        ).fetchall()

        adjusted_topics = []

        for topic in topics:
            base_priority = topic.base_priority_score
            quiz_percentage = topic.quiz_percentage

            if quiz_percentage is None:
                adjustment = 0
                recommendation = "Take a quiz to check your understanding"
            elif quiz_percentage < 60:
                adjustment = base_priority * 0.50
                recommendation = "Needs more practice"
            elif quiz_percentage < 80:
                adjustment = base_priority * 0.20
                recommendation = "Revision recommended"
            else:
                adjustment = -base_priority * 0.20
                recommendation = "Good understanding"

            adjusted_topics.append({
                "id": topic.id,
                "topic_name": topic.topic_name,
                "difficulty": topic.difficulty,
                "importance": topic.importance,
                "estimated_hours": topic.estimated_hours,
                "subject_name": topic.subject_name,
                "total_study_minutes": topic.total_study_minutes,
                "base_priority_score": base_priority,
                "quiz_percentage": quiz_percentage,
                "quiz_attempt_count": topic.quiz_attempt_count,
                "priority_score": base_priority + adjustment,
                "recommendation": recommendation
            })

        adjusted_topics.sort(
            key=lambda topic: topic["priority_score"],
            reverse=True
        )

        focus_topics = adjusted_topics[:3]

        page_size = 6

        try:
            page = int(request.query_params.get("page", 1))
        except (TypeError, ValueError):
            page = 1

        total_topics = len(adjusted_topics)

        total_pages = max(
            1,
            (total_topics + page_size - 1) // page_size
        )

        page = max(1, min(page, total_pages))

        start_index = (page - 1) * page_size
        end_index = start_index + page_size

        topics = adjusted_topics[start_index:end_index]

        completed_sessions = db.execute(
            text("""
                SELECT
                    study_sessions.id,
                    study_sessions.topic_id,
                    study_sessions.started_at,
                    study_sessions.ended_at,
                    study_sessions.duration_minutes
                FROM study_sessions
                JOIN topics
                    ON study_sessions.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE subjects.user_id = :user_id
                  AND study_sessions.ended_at IS NOT NULL
                ORDER BY study_sessions.started_at DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        missed_sessions = db.execute(
            text("""
                SELECT
                    planned_study_sessions.id,
                    planned_study_sessions.topic_id,
                    planned_study_sessions.planned_date,
                    planned_study_sessions.planned_time,
                    planned_study_sessions.planned_minutes,
                    topics.topic_name,
                    subjects.subject_name
                FROM planned_study_sessions
                JOIN topics
                    ON planned_study_sessions.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE planned_study_sessions.user_id = :user_id
                  AND subjects.user_id = :user_id
                  AND planned_study_sessions.status = 'missed'
                ORDER BY
                    planned_study_sessions.planned_date DESC,
                    planned_study_sessions.planned_time DESC
            """),
            {"user_id": user_id}
        ).fetchall()

        planned_sessions = db.execute(
            text("""
                SELECT
                    planned_study_sessions.id,
                    planned_study_sessions.topic_id,
                    planned_study_sessions.planned_date,
                    planned_study_sessions.planned_time,
                    planned_study_sessions.planned_minutes,
                    planned_study_sessions.status,
                    topics.topic_name,
                    subjects.subject_name
                FROM planned_study_sessions
                JOIN topics
                    ON planned_study_sessions.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE planned_study_sessions.user_id = :user_id
                  AND planned_study_sessions.status = 'planned'
                ORDER BY
                    planned_study_sessions.planned_date,
                    planned_study_sessions.planned_time
            """),
            {"user_id": user_id}
        ).fetchall()

        active_session = db.execute(
            text("""
                SELECT
                    study_sessions.id,
                    study_sessions.topic_id,
                    study_sessions.started_at,
                    topics.topic_name,
                    subjects.subject_name
                FROM study_sessions
                JOIN topics
                    ON study_sessions.topic_id = topics.id
                JOIN subjects
                    ON topics.subject_id = subjects.id
                WHERE study_sessions.user_id = :user_id
                  AND study_sessions.ended_at IS NULL
                LIMIT 1
            """),
            {"user_id": user_id}
        ).fetchone()

    finally:
        db.close()

    return templates.TemplateResponse(
        request,
        "study_plan.html",
        {
            "subjects": subjects,
            "topics": topics,
            "focus_topics": focus_topics,
            "total_topics": total_topics,
            "page": page,
            "total_pages": total_pages,
            "syllabi": syllabi,
            "active_session": active_session,
            "completed_sessions": completed_sessions,
            "missed_sessions": missed_sessions,
            "planned_sessions": planned_sessions
        }
    )

@topics_router.post("/study/schedule")
def schedule_study(
    request: Request,
    topic_id: int = Form(...),
    planned_date: date = Form(...),
    planned_time: time = Form(...),
    planned_minutes: int = Form(60)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if planned_minutes < 15 or planned_minutes > 600:
        return RedirectResponse(url="/study-plan", status_code=303)

    scheduled_start = datetime.combine(planned_date, planned_time)
    scheduled_end = scheduled_start + timedelta(minutes=planned_minutes)

    if scheduled_start <= datetime.now():
        return RedirectResponse(url="/study-plan", status_code=303)

    db = SessionLocal()

    try:
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
            return RedirectResponse(url="/study-plan", status_code=303)

        existing_sessions = db.execute(
            text("""
                SELECT
                    planned_time,
                    planned_minutes
                FROM planned_study_sessions
                WHERE user_id = :user_id
                  AND planned_date = :planned_date
                  AND status = 'planned'
            """),
            {
                "user_id": user_id,
                "planned_date": planned_date
            }
        ).fetchall()
        
        
        for session in existing_sessions:
            session_time = session.planned_time

            # MySQL TIME may be returned as timedelta or time.
            if isinstance(session_time, timedelta):
                total_seconds = int(session_time.total_seconds())
                hours = (total_seconds // 3600) % 24
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                session_time = time(hours, minutes, seconds)

            existing_start = datetime.combine(
                planned_date,
                session_time,
            )

            existing_end = existing_start + timedelta(
                minutes=session.planned_minutes
            )

            # Reject only when the two sessions actually overlap.
            if (
                scheduled_start < existing_end
                and scheduled_end > existing_start
            ):
                print("DEBUG: Session rejected due to overlap")
                print(
                    "DEBUG: New session:",
                    scheduled_start,
                    "to",
                    scheduled_end,
                )
                print(
                    "DEBUG: Existing session:",
                    existing_start,
                    "to",
                    existing_end,
                )

                request.session["schedule_message"] = (
                    "Session rejected! This time overlaps with an existing "
                    f"study session from {existing_start.strftime('%I:%M %p')} "
                    f"to {existing_end.strftime('%I:%M %p')}."
                )

                return RedirectResponse(
                    url="/study-plan",
                    status_code=303,
                )

        print("DEBUG: Reached INSERT statement")
        print("DEBUG: Topic ID:", topic_id)
        print("DEBUG: Planned date:", planned_date)
        print("DEBUG: Planned time:", planned_time)

        db.execute(
            text("""
                INSERT INTO planned_study_sessions (
                    user_id,
                    topic_id,
                    planned_date,
                    planned_time,
                    planned_minutes,
                    status,
                    reminder_sent
                )
                VALUES (
                    :user_id,
                    :topic_id,
                    :planned_date,
                    :planned_time,
                    :planned_minutes,
                    'planned',
                    0
                )
            """),
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "planned_date": planned_date,
                "planned_time": planned_time,
                "planned_minutes": planned_minutes
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(url="/study-plan", status_code=303)

@topics_router.post("/study-plan/add-topic")
def add_topic(
    request: Request,
    subject_id: int = Form(...),
    topic_name: str = Form(...),
    difficulty: int = Form(...),
    importance: int = Form(...),
    estimated_hours: float = Form(...)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    topic_name = topic_name.strip()

    if not topic_name:
        return RedirectResponse(url="/study-plan", status_code=303)

    if difficulty not in range(1, 6):
        return RedirectResponse(url="/study-plan", status_code=303)

    if importance not in range(1, 6):
        return RedirectResponse(url="/study-plan", status_code=303)

    if estimated_hours <= 0:
        return RedirectResponse(url="/study-plan", status_code=303)

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
            return RedirectResponse(url="/study-plan", status_code=303)

        db.execute(
            text("""
                INSERT INTO topics (
                    subject_id,
                    topic_name,
                    difficulty,
                    importance,
                    estimated_hours
                )
                VALUES (
                    :subject_id,
                    :topic_name,
                    :difficulty,
                    :importance,
                    :estimated_hours
                )
            """),
            {
                "subject_id": subject_id,
                "topic_name": topic_name,
                "difficulty": difficulty,
                "importance": importance,
                "estimated_hours": estimated_hours
            }
        )

        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()

    return RedirectResponse(url="/study-plan", status_code=303)
