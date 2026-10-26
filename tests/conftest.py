from app.routes import topics as topics_routes
import pytest
from urllib.parse import quote_plus

from app.routes import syllabus as syllabus_routes
from app.routes import ai as ai_routes

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.main import app
from app.database import (
    Base,
    DB_USER,
    DB_PASSWORD,
    DB_HOST,
    DB_PORT,
    get_db,
)


TEST_DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/study_plan_test"
)

test_engine = create_engine(TEST_DATABASE_URL)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    # Register SQLAlchemy models before creating their tables.
    import app.models

    # Create ORM-managed tables, such as users.
    Base.metadata.create_all(bind=test_engine)

    # Create tables used by raw SQL routes.
    with test_engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS subjects (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                subject_name VARCHAR(100) NOT NULL,
                KEY user_id (user_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS password_reset_tokens (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                token_hash VARCHAR(64) NOT NULL UNIQUE,
                expires_at DATETIME NOT NULL,
                used_at DATETIME NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                KEY user_id (user_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS planned_study_sessions (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                topic_id INT NOT NULL,
                planned_date DATE NOT NULL,
                planned_time TIME NOT NULL,
                planned_minutes INT NOT NULL DEFAULT 60,
                status VARCHAR(20) NOT NULL DEFAULT 'planned',
                reminder_sent TINYINT(1) NOT NULL DEFAULT 0,
                KEY user_id (user_id),
                KEY topic_id (topic_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS topics (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                subject_id INT NOT NULL,
                topic_name VARCHAR(150) NOT NULL,
                difficulty INT DEFAULT 3,
                importance INT DEFAULT 3,
                estimated_hours FLOAT DEFAULT 1,
                KEY subject_id (subject_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS syllabi (
               id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
               subject_id INT NOT NULL,
               file_name VARCHAR(255) NOT NULL,
               file_path VARCHAR(500) NOT NULL,
               extracted_text LONGTEXT,
               processing_status VARCHAR(30) DEFAULT 'uploaded',
               uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               KEY subject_id (subject_id)
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS study_sessions (
                id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                topic_id INT NOT NULL,
                started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                ended_at DATETIME DEFAULT NULL,
                duration_minutes INT DEFAULT NULL,
                duration_seconds INT DEFAULT NULL,
                KEY user_id (user_id),
                KEY topic_id (topic_id)
            )
        """))

    yield

    # Remove raw-SQL tables created for this test setup.
    with test_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS study_sessions"))
        conn.execute(text("DROP TABLE IF EXISTS topics"))
        conn.execute(text("DROP TABLE IF EXISTS syllabi"))
        conn.execute(text("DROP TABLE IF EXISTS subjects"))
        conn.execute(
            text("DROP TABLE IF EXISTS planned_study_sessions")
        )
        conn.execute(
            text("DROP TABLE IF EXISTS password_reset_tokens")
        )

    # Remove ORM-managed test tables.
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()


@pytest.fixture(autouse=True)
def clean_test_data():
    # Clear test records before each test.
    with test_engine.begin() as conn:
        conn.execute(text("DELETE FROM password_reset_tokens"))
        conn.execute(text("DELETE FROM study_sessions"))
        conn.execute(text("DELETE FROM planned_study_sessions"))
        conn.execute(text("DELETE FROM syllabi"))
        conn.execute(text("DELETE FROM topics"))
        conn.execute(text("DELETE FROM subjects"))

    # Reset ORM-managed tables, including users.
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    yield


@pytest.fixture
def client(monkeypatch):
    from app.routes import study_sessions as study_sessions_routes
    from app import password_reset as password_reset_module

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # Routes using dependency injection use the test database.
    app.dependency_overrides[get_db] = override_get_db

    # Routes using SessionLocal directly also use the test database.
    monkeypatch.setattr(
        study_sessions_routes,
        "SessionLocal",
        TestingSessionLocal,
    )
    monkeypatch.setattr(
        syllabus_routes,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        ai_routes,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        password_reset_module,
        "SessionLocal",
        TestingSessionLocal,
    )

    monkeypatch.setattr(
        topics_routes,
        "SessionLocal",
        TestingSessionLocal,
    )

    test_client = TestClient(app)

    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.pop(get_db, None)

