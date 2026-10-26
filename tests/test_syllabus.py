
import io
import json

from pypdf import PdfWriter
from sqlalchemy import text


def create_pdf_bytes():
    """Create a small valid PDF for upload testing."""
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(buffer)
    return buffer.getvalue()


def create_logged_in_client(client):
    """Register and log in a test student."""
    user_data = {
        "name": "Syllabus Test Student",
        "email": "syllabus.test@example.com",
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
            "email": user_data["email"],
            "password": user_data["password"],
        },
    )
    assert login_response.status_code == 200

    return login_response.json()["user_id"]


def create_subject(user_id, subject_name="Computer Networks"):
    """Create a subject in the test database."""
    from tests.conftest import TestingSessionLocal

    db = TestingSessionLocal()
    try:
        result = db.execute(
            text("""
                INSERT INTO subjects (user_id, subject_name)
                VALUES (:user_id, :subject_name)
            """),
            {
                "user_id": user_id,
                "subject_name": subject_name,
            },
        )
        db.commit()
        return result.lastrowid
    finally:
        db.close()


def test_syllabus_upload_requires_login(client):
    response = client.post(
        "/syllabus/upload",
        data={"subject_id": "1"},
        files={
            "syllabus_file": (
                "sample.pdf",
                create_pdf_bytes(),
                "application/pdf",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_syllabus_upload_rejects_non_pdf(client):
    user_id = create_logged_in_client(client)
    subject_id = create_subject(user_id)

    response = client.post(
        "/syllabus/upload",
        data={"subject_id": str(subject_id)},
        files={
            "syllabus_file": (
                "notes.txt",
                b"This is not a PDF",
                "text/plain",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_syllabus_upload_rejects_invalid_pdf_content(client):
    user_id = create_logged_in_client(client)
    subject_id = create_subject(user_id)

    response = client.post(
        "/syllabus/upload",
        data={"subject_id": str(subject_id)},
        files={
            "syllabus_file": (
                "invalid.pdf",
                b"This is not really a PDF",
                "application/pdf",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_syllabus_upload_rejects_another_users_subject(client):
    user_id = create_logged_in_client(client)
    other_user_id = user_id + 10000
    subject_id = create_subject(
        other_user_id,
        "Another Student's Subject",
    )

    response = client.post(
        "/syllabus/upload",
        data={"subject_id": str(subject_id)},
        files={
            "syllabus_file": (
                "sample.pdf",
                create_pdf_bytes(),
                "application/pdf",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"


def test_ai_topic_generation_requires_login(client):
    response = client.post(
        "/ai/generate-topics",
        data={"syllabus_id": "1"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_ai_topic_generation_rejects_unknown_syllabus(client):
    user_id = create_logged_in_client(client)

    response = client.post(
        "/ai/generate-topics",
        data={"syllabus_id": "999999"},
    )

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_ai_topic_generation_saves_mocked_topics(
    client,
    monkeypatch,
):
    from app.routes import ai as ai_routes
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    subject_id = create_subject(user_id)

    db = TestingSessionLocal()
    try:
        result = db.execute(
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
                "file_name": "networks.pdf",
                "file_path": "test-networks.pdf",
                "extracted_text": (
                    "Computer Networks: OSI model, TCP/IP, "
                    "network devices and routing."
                ),
                "processing_status": "extracted",
            },
        )
        syllabus_id = result.lastrowid
        db.commit()
    finally:
        db.close()

    fake_response_text = json.dumps({
        "topics": [
            {
                "topic_name": "OSI Model",
                "content_covered": "Seven layers of networking",
                "difficulty": 3,
                "importance": 5,
                "estimated_hours": 2,
            },
            {
                "topic_name": "TCP/IP",
                "content_covered": "Internet protocol suite",
                "difficulty": 4,
                "importance": 5,
                "estimated_hours": 3,
            },
        ]
    })

    class FakeMessage:
        content = fake_response_text

    class FakeChoice:
        message = FakeMessage()

    class FakeCompletion:
        choices = [FakeChoice()]

    class FakeCompletions:
        @staticmethod
        def create(**kwargs):
            assert kwargs["model"] == "openai/gpt-oss-20b"
            return FakeCompletion()

    class FakeChat:
        completions = FakeCompletions()

    class FakeGroq:
        def __init__(self, api_key):
            self.chat = FakeChat()

    monkeypatch.setattr(ai_routes, "Groq", FakeGroq)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")

    response = client.post(
        "/ai/generate-topics",
        data={"syllabus_id": str(syllabus_id)},
    )

    assert response.status_code == 200
    assert "OSI Model" in response.text
    assert "TCP/IP" in response.text

    db = TestingSessionLocal()
    try:
        saved_topics = db.execute(
            text("""
                SELECT topic_name, difficulty, importance, estimated_hours
                FROM topics
                WHERE subject_id = :subject_id
                ORDER BY id
            """),
            {"subject_id": subject_id},
        ).all()

        assert len(saved_topics) == 2
        assert saved_topics[0].topic_name == "OSI Model"
        assert saved_topics[0].difficulty == 3
        assert saved_topics[0].importance == 5
        assert saved_topics[0].estimated_hours == 2
        assert saved_topics[1].topic_name == "TCP/IP"
    finally:
        db.close()

def test_syllabus_upload_saves_pdf_and_extracted_text(
    client,
    monkeypatch,
    tmp_path,
):
    from app.routes import syllabus as syllabus_routes
    from tests.conftest import TestingSessionLocal

    user_id = create_logged_in_client(client)
    subject_id = create_subject(user_id)

    # Keep the uploaded file inside pytest's temporary directory.
    monkeypatch.setattr(syllabus_routes, "UPLOAD_DIR", tmp_path)

    # Simulate readable text extracted from a PDF.
    class FakePage:
        @staticmethod
        def extract_text():
            return "Computer Networks: OSI model and TCP/IP."

    class FakePdfReader:
        is_encrypted = False
        pages = [FakePage()]

    monkeypatch.setattr(
        syllabus_routes,
        "PdfReader",
        lambda _: FakePdfReader(),
    )

    response = client.post(
        "/syllabus/upload",
        data={"subject_id": str(subject_id)},
        files={
            "syllabus_file": (
                "computer_networks.pdf",
                create_pdf_bytes(),
                "application/pdf",
            )
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/subjects"

    db = TestingSessionLocal()
    try:
        syllabus = db.execute(
            text("""
                SELECT file_name, file_path, extracted_text,
                       processing_status
                FROM syllabi
                WHERE subject_id = :subject_id
            """),
            {"subject_id": subject_id},
        ).first()

        assert syllabus is not None
        assert syllabus.file_name == "computer_networks.pdf"
        assert syllabus.extracted_text == (
            "Computer Networks: OSI model and TCP/IP."
        )
        assert syllabus.processing_status == "extracted"
        assert (tmp_path / syllabus.file_path.split("/")[-1]).exists()
    finally:
        db.close()