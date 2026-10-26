
from sqlalchemy import text


def register_and_login(client, email="study.test@example.com"):
    user_data = {
        "name": "Study Session Test User",
        "email": email,
        "password": "TestPassword123",
    }

    register_response = client.post(
        "/users/register",
        json=user_data,
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/users/login",
        json={
            "email": email,
            "password": user_data["password"],
        },
    )
    assert login_response.status_code == 200

    return login_response.json()["user_id"]


def create_topic(user_id):
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()

    try:
        subject_result = db.execute(
            text("""
                INSERT INTO subjects (user_id, subject_name)
                VALUES (:user_id, :subject_name)
            """),
            {
                "user_id": user_id,
                "subject_name": "Test Computer Networks",
            },
        )

        subject_id = subject_result.lastrowid

        topic_result = db.execute(
            text("""
                INSERT INTO topics
                    (subject_id, topic_name, difficulty, importance, estimated_hours)
                VALUES
                    (:subject_id, :topic_name, 3, 3, 1)
            """),
            {
                "subject_id": subject_id,
                "topic_name": "Test OSI Model",
            },
        )

        topic_id = topic_result.lastrowid
        db.commit()

        return topic_id

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def test_start_study_requires_login(client):
    response = client.post(
        "/study/start",
        data={"topic_id": 1},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_stop_study_requires_login(client):
    response = client.post(
        "/study/stop",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_start_study_creates_active_session(client):
    user_id = register_and_login(client)
    topic_id = create_topic(user_id)

    response = client.post(
        "/study/start",
        data={"topic_id": topic_id},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"

    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        session = db.execute(
            text("""
                SELECT user_id, topic_id, ended_at
                FROM study_sessions
                WHERE user_id = :user_id
            """),
            {"user_id": user_id},
        ).fetchone()

        assert session is not None
        assert session.user_id == user_id
        assert session.topic_id == topic_id
        assert session.ended_at is None
    finally:
        db.close()


def test_start_study_rejects_invalid_topic(client):
    register_and_login(client)

    response = client.post(
        "/study/start",
        data={"topic_id": 999999},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"


def test_start_study_prevents_duplicate_active_sessions(client):
    user_id = register_and_login(client)
    topic_id = create_topic(user_id)

    first_response = client.post(
        "/study/start",
        data={"topic_id": topic_id},
        follow_redirects=False,
    )
    assert first_response.status_code == 303

    second_response = client.post(
        "/study/start",
        data={"topic_id": topic_id},
        follow_redirects=False,
    )
    assert second_response.status_code == 303

    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM study_sessions
                WHERE user_id = :user_id
                  AND ended_at IS NULL
            """),
            {"user_id": user_id},
        ).scalar_one()

        assert count == 1
    finally:
        db.close()


def test_stop_study_without_active_session_redirects(client):
    register_and_login(client)

    response = client.post(
        "/study/stop",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_stop_study_finishes_active_session(client):
    user_id = register_and_login(client)
    topic_id = create_topic(user_id)

    start_response = client.post(
        "/study/start",
        data={"topic_id": topic_id},
        follow_redirects=False,
    )
    assert start_response.status_code == 303

    response = client.post(
        "/study/stop",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/study-plan"

    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        session = db.execute(
            text("""
                SELECT ended_at, duration_seconds, duration_minutes
                FROM study_sessions
                WHERE user_id = :user_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {"user_id": user_id},
        ).fetchone()

        assert session is not None
        assert session.ended_at is not None
        assert session.duration_seconds is not None
        assert session.duration_minutes is not None
        assert session.duration_seconds >= 0
        assert session.duration_minutes >= 0
    finally:
        db.close()
