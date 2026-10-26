
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from tests.test_syllabus import (
    create_logged_in_client,
    create_subject,
)


def create_topic(user_id, topic_name="OSI Model"):
    from tests.conftest import TestingSessionLocal

    subject_id = create_subject(user_id)

    db = TestingSessionLocal()
    try:
        result = db.execute(
            text("""
                INSERT INTO topics (
                    subject_id, topic_name, difficulty,
                    importance, estimated_hours
                )
                VALUES (
                    :subject_id, :topic_name, 3, 5, 2
                )
            """),
            {
                "subject_id": subject_id,
                "topic_name": topic_name,
            },
        )
        db.commit()
        return result.lastrowid
    finally:
        db.close()


def future_slot():
    start = datetime.now() + timedelta(days=2)
    start = start.replace(second=0, microsecond=0)
    return start.date(), start.time()


def test_schedule_study_requires_login(client):
    planned_date, planned_time = future_slot()

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": "1",
            "planned_date": planned_date.isoformat(),
            "planned_time": planned_time.strftime("%H:%M"),
            "planned_minutes": "60",
        },
        follow_redirects=False,
    )

    print("Response status:", response.status_code)
    print("Redirect location:", response.headers.get("location"))
    print("Session message:", client.cookies)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_schedule_study_saves_session(client):
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    planned_date, planned_time = future_slot()

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": str(topic_id),
            "planned_date": planned_date.isoformat(),
            "planned_time": planned_time.strftime("%H:%M"),
            "planned_minutes": "60",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"

    db = TestingSessionLocal()
    try:
        session = db.execute(
            text("""
                SELECT user_id, topic_id, planned_date,
                       planned_time, planned_minutes,
                       status, reminder_sent
                FROM planned_study_sessions
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).first()

        assert session is not None
        assert session.topic_id == topic_id
        assert session.planned_minutes == 60
        assert session.status == "planned"
        assert session.reminder_sent == 0
    finally:
        db.close()


def test_schedule_study_rejects_too_short_duration(client):
    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    planned_date, planned_time = future_slot()

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": str(topic_id),
            "planned_date": planned_date.isoformat(),
            "planned_time": planned_time.strftime("%H:%M"),
            "planned_minutes": "10",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"


def test_schedule_study_rejects_past_time(client):
    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)

    past = datetime.now() - timedelta(days=1)

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": str(topic_id),
            "planned_date": past.date().isoformat(),
            "planned_time": past.time().strftime("%H:%M"),
            "planned_minutes": "60",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"


def test_schedule_study_rejects_another_users_topic(client):
    user_id = create_logged_in_client(client)
    other_user_id = user_id + 10000
    topic_id = create_topic(other_user_id)
    planned_date, planned_time = future_slot()

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": str(topic_id),
            "planned_date": planned_date.isoformat(),
            "planned_time": planned_time.strftime("%H:%M"),
            "planned_minutes": "60",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"

    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM planned_study_sessions
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).scalar_one()

        assert count == 0
    finally:
        db.close()


def test_schedule_study_rejects_overlapping_session(client):
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    planned_date, planned_time = future_slot()

    db = TestingSessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO planned_study_sessions (
                    user_id, topic_id, planned_date, planned_time,
                    planned_minutes, status, reminder_sent
                )
                VALUES (
                    :user_id, :topic_id, :planned_date, :planned_time,
                    60, 'planned', 0
                )
            """),
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "planned_date": planned_date,
                "planned_time": planned_time,
            },
        )
        db.commit()
    finally:
        db.close()

    # Try scheduling another session 30 minutes later.
    overlapping_time = (
        datetime.combine(planned_date, planned_time)
        + timedelta(minutes=30)
    ).time()

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": str(topic_id),
            "planned_date": planned_date.isoformat(),
            "planned_time": overlapping_time.strftime("%H:%M"),
            "planned_minutes": "60",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"

    db = TestingSessionLocal()
    try:
        count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM planned_study_sessions
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).scalar_one()

        assert count == 1
    finally:
        db.close()


def create_past_planned_session(user_id, topic_id):
    from tests.conftest import TestingSessionLocal

    past = datetime.now() - timedelta(hours=2)

    db = TestingSessionLocal()
    try:
        result = db.execute(
            text("""
                INSERT INTO planned_study_sessions (
                    user_id, topic_id, planned_date, planned_time,
                    planned_minutes, status, reminder_sent
                )
                VALUES (
                    :user_id, :topic_id, :planned_date, :planned_time,
                    60, 'planned', 0
                )
            """),
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "planned_date": past.date(),
                "planned_time": past.time().replace(microsecond=0),
            },
        )
        db.commit()
        return result.lastrowid
    finally:
        db.close()


def test_missed_session_sends_email_and_updates_status(
    client,
    monkeypatch,
):
    import importlib

    topics_routes = importlib.import_module("app.reminders")
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    session_id = create_past_planned_session(user_id, topic_id)

    sent_emails = []

    def fake_send_email(**kwargs):
        sent_emails.append(kwargs)

    monkeypatch.setattr(
        topics_routes,
        "SessionLocal",
        TestingSessionLocal,
    )
    monkeypatch.setattr(
        topics_routes,
        "send_missed_study_email",
        fake_send_email,
    )

    topics_routes.check_missed_study_sessions()

    assert len(sent_emails) == 1
    assert sent_emails[0]["recipient"] == "syllabus.test@example.com"
    assert sent_emails[0]["topic_name"] == "OSI Model"

    db = TestingSessionLocal()
    try:
        session = db.execute(
            text("""
                SELECT status, reminder_sent
                FROM planned_study_sessions
                WHERE id = :session_id
            """),
            {"session_id": session_id},
        ).first()

        assert session.status == "missed"
        assert session.reminder_sent == 1
    finally:
        db.close()


def test_missed_session_email_failure_allows_retry(
    client,
    monkeypatch,
):
    import importlib

    topics_routes = importlib.import_module("app.reminders")
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    session_id = create_past_planned_session(user_id, topic_id)

    attempts = []

    def fake_send_email(**kwargs):
        attempts.append(kwargs)
        raise RuntimeError("Simulated email failure")

    monkeypatch.setattr(
        topics_routes,
        "SessionLocal",
        TestingSessionLocal,
    )
    monkeypatch.setattr(
        topics_routes,
        "send_missed_study_email",
        fake_send_email,
    )

    topics_routes.check_missed_study_sessions()

    assert len(attempts) == 1

    db = TestingSessionLocal()
    try:
        session = db.execute(
            text("""
                SELECT status, reminder_sent
                FROM planned_study_sessions
                WHERE id = :session_id
            """),
            {"session_id": session_id},
        ).first()

        assert session.status == "planned"
        assert session.reminder_sent == 0
    finally:
        db.close()


def test_missed_session_email_is_not_sent_twice(
    client,
    monkeypatch,
):
    import importlib

    topics_routes = importlib.import_module("app.reminders")
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    create_past_planned_session(user_id, topic_id)

    sent_emails = []

    def fake_send_email(**kwargs):
        sent_emails.append(kwargs)

    monkeypatch.setattr(
        topics_routes,
        "SessionLocal",
        TestingSessionLocal,
    )
    monkeypatch.setattr(
        topics_routes,
        "send_missed_study_email",
        fake_send_email,
    )

    topics_routes.check_missed_study_sessions()
    topics_routes.check_missed_study_sessions()

    assert len(sent_emails) == 1

    
def test_schedule_study_allows_back_to_back_sessions(client):
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    topic_id = create_topic(user_id)
    planned_date, planned_time = future_slot()

    # First session: 10:00–11:00, using the selected future date.
    first_start = datetime.combine(
        planned_date,
        time(10, 0),
    )

    # Ensure the selected date/time is in the future.
    if first_start <= datetime.now():
        first_start += timedelta(days=1)
        planned_date = first_start.date()

    db = TestingSessionLocal()
    try:
        db.execute(
            text("""
                INSERT INTO planned_study_sessions (
                    user_id, topic_id, planned_date, planned_time,
                    planned_minutes, status, reminder_sent
                )
                VALUES (
                    :user_id, :topic_id, :planned_date, :planned_time,
                    60, 'planned', 0
                )
            """),
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "planned_date": planned_date,
                "planned_time": time(10, 0),
            },
        )
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/study/schedule",
        data={
            "topic_id": str(topic_id),
            "planned_date": planned_date.isoformat(),
            "planned_time": "11:00",
            "planned_minutes": "60",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"

    db = TestingSessionLocal()
    try:
        count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM planned_study_sessions
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).scalar_one()

        assert count == 2
    finally:
        db.close()
