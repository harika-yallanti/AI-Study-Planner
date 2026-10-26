import os
import json

from dotenv import load_dotenv
from fastapi import APIRouter, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy import text
from groq import Groq

from app.database import SessionLocal


load_dotenv()

ai_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# GENERATE STUDY TOPICS FROM SYLLABUS
@ai_router.post("/ai/generate-topics")
def generate_topics(
    request: Request,
    syllabus_id: int = Form(...)
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:
        syllabus = db.execute(
            text("""
                SELECT
                    syllabi.id,
                    syllabi.subject_id,
                    syllabi.extracted_text,
                    syllabi.processing_status,
                    subjects.subject_name
                FROM syllabi
                JOIN subjects
                    ON syllabi.subject_id = subjects.id
                WHERE syllabi.id = :syllabus_id
                AND subjects.user_id = :user_id
            """),
            {
                "syllabus_id": syllabus_id,
                "user_id": user_id
            }
        ).first()

        if not syllabus:
            return templates.TemplateResponse(
                request,
                "ai_topics.html",
                {
                    "topics": [],
                    "subject_name": None,
                    "syllabus_id": syllabus_id,
                    "error": "The selected syllabus was not found."
                },
                status_code=404
            )

        if syllabus.processing_status != "extracted":
            return templates.TemplateResponse(
                request,
                "ai_topics.html",
                {
                    "topics": [],
                    "subject_name": syllabus.subject_name,
                    "syllabus_id": syllabus_id,
                    "error": "The syllabus text is not ready for AI analysis."
                }
            )

        syllabus_text = syllabus.extracted_text
        subject_name = syllabus.subject_name
        subject_id = syllabus.subject_id

    finally:
        db.close()

    if not syllabus_text or not syllabus_text.strip():
        return templates.TemplateResponse(
            request,
            "ai_topics.html",
            {
                "topics": [],
                "subject_name": subject_name,
                "syllabus_id": syllabus_id,
                "error": "No readable text was found in this syllabus."
            }
        )
            # Check Groq API key
    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return templates.TemplateResponse(
            request,
            "ai_topics.html",
            {
                "topics": [],
                "subject_name": subject_name,
                "syllabus_id": syllabus_id,
                "error": "Groq API key is not configured."
            }
        )

    # Generate topics using Groq
    try:
        client = Groq(api_key=api_key)

        prompt = f"""
Analyze this college syllabus for the subject:
{subject_name}

Generate a comprehensive, organized list of study topics.

Rules:
- Use only concepts present in the syllabus.
- Organize topics by major concepts or units.
- Combine closely related subtopics into one topic.
- Do not create multiple topics with different names
  for the same concept.
- Keep distinct concepts separate when they require
  different study material.
- Do not create a separate topic for a subtopic
  already covered by a broader topic.
- Include important concepts from the syllabus.
- Difficulty and importance must be integers from 1 to 5.
- Estimated study hours must be a positive number.
- Return only valid JSON without Markdown.

Return this format:
{{
    "topics": [
        {{
            "topic_name": "Topic name",
            "content_covered": "Concepts covered",
            "difficulty": 3,
            "importance": 4,
            "estimated_hours": 3
        }}
    ]
}}

Syllabus content:
{syllabus_text}
"""

        response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze college syllabi and generate study topics. "
                    "Return one valid JSON object only. "
                    "Do not include Markdown, explanations, or text outside JSON."
                )
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={"type": "json_object"},
        temperature=0.2,
        max_tokens=6000
        )

        response_text = response.choices[0].message.content

        if not response_text:
            raise ValueError("Groq returned an empty response.")

        data = json.loads(response_text)
        topics = data.get("topics", [])

        if not isinstance(topics, list) or not topics:
            raise ValueError("Invalid topics format.")

        validated_topics = []
        generated_names = set()

        for topic in topics:

            if not isinstance(topic, dict):
                raise ValueError("Invalid topic format.")

            topic_name = topic.get("topic_name")
            content_covered = topic.get("content_covered")
            difficulty = topic.get("difficulty")
            importance = topic.get("importance")
            estimated_hours = topic.get("estimated_hours")

            if not isinstance(topic_name, str) or not topic_name.strip():
                raise ValueError("Invalid topic name.")

            if not isinstance(content_covered, str):
                raise ValueError("Invalid topic description.")

            if (
                not isinstance(difficulty, int)
                or isinstance(difficulty, bool)
                or not 1 <= difficulty <= 5
            ):
                raise ValueError("Invalid topic difficulty.")

            if (
                not isinstance(importance, int)
                or isinstance(importance, bool)
                or not 1 <= importance <= 5
            ):
                raise ValueError("Invalid topic importance.")

            if (
                not isinstance(estimated_hours, (int, float))
                or isinstance(estimated_hours, bool)
                or estimated_hours <= 0
            ):
                raise ValueError("Invalid topic study hours.")

            topic_name = topic_name.strip()
            content_covered = content_covered.strip()

            normalized_name = " ".join(
                topic_name.lower().split()
            )

            if normalized_name in generated_names:
                continue

            generated_names.add(normalized_name)

            validated_topics.append({
                "topic_name": topic_name,
                "content_covered": content_covered,
                "difficulty": difficulty,
                "importance": importance,
                "estimated_hours": estimated_hours
            })

        if not validated_topics:
            raise ValueError("No valid topics were generated.")

        topics = validated_topics

    except Exception as e:

        print("Groq topic generation error:", repr(e))

        error_text = str(e).lower()

        if (
            "429" in error_text
            or "rate_limit" in error_text
            or "quota" in error_text
        ):
            error_message = (
                "Groq's usage limit has been reached. "
                "Please wait and try again later."
            )

        elif "timeout" in error_text:
            error_message = (
                "Groq took too long to respond. "
                "Please check your internet connection and try again."
            )

        elif "503" in error_text or "unavailable" in error_text:
            error_message = (
                "The AI model is temporarily busy. "
                "Please wait a minute and try again."
            )

        else:
            error_message = (
                "Unable to generate study topics right now. "
                "Please try again later."
            )

        return templates.TemplateResponse(
            request,
            "ai_topics.html",
            {
                "topics": [],
                "subject_name": subject_name,
                "syllabus_id": syllabus_id,
                "error": error_message
            },
            status_code=503
        )

    # Save generated topics to database
    db = SessionLocal()

    try:

        existing_topics = db.execute(
            text("""
                SELECT topic_name
                FROM topics
                WHERE subject_id = :subject_id
            """),
            {
                "subject_id": subject_id
            }
        ).all()

        existing_names = {
            " ".join(row.topic_name.lower().split())
            for row in existing_topics
        }

        saved_topics = []
        skipped_count = 0

        for topic in topics:

            topic_name = topic["topic_name"]

            normalized_name = " ".join(
                topic_name.lower().split()
            )

            if normalized_name in existing_names:
                skipped_count += 1
                continue

            result = db.execute(
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
                    "difficulty": topic["difficulty"],
                    "importance": topic["importance"],
                    "estimated_hours": topic["estimated_hours"]
                }
            )

            topic["id"] = result.lastrowid

            saved_topics.append(topic)

            existing_names.add(normalized_name)

        db.commit()

        print("Topics saved:", len(saved_topics))
        print("Duplicate topics skipped:", skipped_count)

    except Exception as e:

        db.rollback()

        print("Topic database saving error:", repr(e))

        return templates.TemplateResponse(
            request,
            "ai_topics.html",
            {
                "topics": [],
                "subject_name": subject_name,
                "syllabus_id": syllabus_id,
                "error": "Unable to save generated topics to the database."
            },
            status_code=500
        )

    finally:
        db.close()

    # Fetch all topics for the subject
    db = SessionLocal()

    try:

        all_topics = db.execute(
            text("""
                SELECT
                    id,
                    topic_name,
                    difficulty,
                    importance,
                    estimated_hours
                FROM topics
                WHERE subject_id = :subject_id
                ORDER BY id
            """),
            {
                "subject_id": subject_id
            }
        ).mappings().all()

        all_topics = [
            dict(topic)
            for topic in all_topics
        ]

    finally:
        db.close()

    if not saved_topics:
        error_message = (
            "No new topics were added. "
            "Showing existing topics for this subject."
        )
    else:
        error_message = None

    return templates.TemplateResponse(
        request,
        "ai_topics.html",
        {
            "subject_name": subject_name,
            "topics": all_topics,
            "syllabus_id": syllabus_id,
            "error": error_message
        }
    )



# GENERATE QUIZ FOR A SELECTED TOPIC


@ai_router.post("/ai/generate-quiz")
def generate_quiz(
    request: Request,
    syllabus_id: int = Form(...),
    topic_id: int = Form(...),
    topic_name: str = Form(...),
    content_covered: str = Form("")
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    db = SessionLocal()

    try:

        syllabus = db.execute(
            text("""
                SELECT
                    syllabi.extracted_text,
                    syllabi.processing_status,
                    subjects.subject_name,
                    subjects.id AS subject_id
                FROM syllabi
                JOIN subjects
                    ON syllabi.subject_id = subjects.id
                WHERE syllabi.id = :syllabus_id
                AND subjects.user_id = :user_id
            """),
            {
                "syllabus_id": syllabus_id,
                "user_id": user_id
            }
        ).first()

        if not syllabus:
            return templates.TemplateResponse(
                request,
                "ai_quiz.html",
                {
                    "error": "The selected syllabus was not found.",
                    "questions": [],
                    "topic_name": topic_name,
                    "topic_id": topic_id
                },
                status_code=404
            )

        topic = db.execute(
            text("""
                SELECT
                    id,
                    topic_name
                FROM topics
                WHERE id = :topic_id
                AND subject_id = :subject_id
            """),
            {
                "topic_id": topic_id,
                "subject_id": syllabus.subject_id
            }
        ).first()

        if not topic:
            return templates.TemplateResponse(
                request,
                "ai_quiz.html",
                {
                    "error": (
                        "The selected topic was not found "
                        "in this subject. Please generate topics again."
                    ),
                    "questions": [],
                    "topic_name": topic_name,
                    "topic_id": topic_id
                },
                status_code=404
            )

        topic_name = topic.topic_name

        # Use the submitted topic description,
        # or fall back to the saved topic name.
        content_covered = (
            content_covered.strip()
            or topic_name
        )

        if syllabus.processing_status != "extracted":
            return templates.TemplateResponse(
                request,
                "ai_quiz.html",
                {
                    "error": (
                        "The syllabus is not ready "
                        "for quiz generation."
                    ),
                    "questions": [],
                    "topic_name": topic_name,
                    "topic_id": topic_id
                }
            )

        syllabus_text = syllabus.extracted_text
        subject_name = syllabus.subject_name

    finally:
        db.close()

    if not syllabus_text or not syllabus_text.strip():
        return templates.TemplateResponse(
            request,
            "ai_quiz.html",
            {
                "error": "No readable syllabus content was found.",
                "questions": [],
                "topic_name": topic_name,
                "topic_id": topic_id
            }
        )

    api_key = os.getenv("GROQ_API_KEY")

    if not api_key:
        return templates.TemplateResponse(
            request,
            "ai_quiz.html",
            {
                "error": "Groq API key is not configured.",
                "questions": [],
                "topic_name": topic_name,
                "topic_id": topic_id
            }
        )

    # Generate quiz using Groq
    try:

        client = Groq(api_key=api_key)

        prompt = f"""
Create a quiz for a college student.

Subject: {subject_name}

Selected topic: {topic_name}

Topic description:
{content_covered}

Generate exactly 5 multiple-choice questions.

Important rules:
- Questions must focus only on the selected topic.
- Use the syllabus as the source of truth.
- Do not ask questions about unrelated topics.
- Avoid questions that are too simple or repetitive.
- Include conceptual and application-based questions.
- Make the questions suitable for a college-level student.

Each question must contain:
- question: The question text
- options: Exactly 4 answer choices
- correct_answer: The correct answer letter (A, B, C, or D)
- explanation: A short explanation of why the answer is correct

Return only valid JSON in this format:

{{
    "questions": [
        {{
            "question": "Question text",
            "options": {{
                "A": "First answer",
                "B": "Second answer",
                "C": "Third answer",
                "D": "Fourth answer"
            }},
            "correct_answer": "B",
            "explanation": "Explanation"
        }}
    ]
}}

Syllabus content:
{syllabus_text}
"""

        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate accurate educational "
                        "quiz questions. Return only valid "
                        "JSON matching the requested format."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={
                "type": "json_object"
            },
            temperature=0.3
        )

        response_text = response.choices[0].message.content

        if not response_text:
            raise ValueError("Groq returned an empty response.")

        data = json.loads(response_text)

        questions = data.get("questions", [])

        if not isinstance(questions, list) or len(questions) != 5:
            raise ValueError("Invalid quiz questions.")

        for question in questions:

            if not isinstance(question, dict):
                raise ValueError("Invalid quiz question format.")

            options = question.get("options")

            if not isinstance(options, dict):
                raise ValueError("Invalid quiz options.")

            if set(options.keys()) != {"A", "B", "C", "D"}:
                raise ValueError("Each question must have four options.")

            if question.get("correct_answer") not in {
                "A", "B", "C", "D"
            }:
                raise ValueError("Invalid correct answer.")

            if not isinstance(question.get("question"), str):
                raise ValueError("Invalid question text.")

            if not isinstance(question.get("explanation"), str):
                raise ValueError("Invalid explanation.")

            if not all(
                isinstance(options[letter], str)
                and options[letter].strip()
                for letter in ["A", "B", "C", "D"]
            ):
                raise ValueError("Invalid answer options.")

    except Exception as e:

        print("Groq quiz generation error:", repr(e))

        error_text = str(e).lower()

        if "429" in error_text or "rate_limit" in error_text:
            error_message = (
                "Groq's usage limit has been reached. "
                "Please wait and try again later."
            )

        elif "timeout" in error_text:
            error_message = (
                "Groq took too long to respond. "
                "Please check your internet connection and try again."
            )

        elif "503" in error_text or "unavailable" in error_text:
            error_message = (
                "The AI model is temporarily busy. "
                "Please try again in a minute."
            )

        else:
            error_message = (
                "Unable to generate the quiz right now. "
                "Please try again later."
            )

        return templates.TemplateResponse(
            request,
            "ai_quiz.html",
            {
                "error": error_message,
                "questions": [],
                "topic_name": topic_name,
                "topic_id": topic_id
            },
            status_code=503
        )

    return templates.TemplateResponse(
        request,
        "ai_quiz.html",
        {
            "topic_name": topic_name,
            "subject_name": subject_name,
            "topic_id": topic_id,
            "questions": questions,
            "error": None
        }
    )



# SAVE QUIZ SCORE

@ai_router.post("/ai/save-quiz-score")
def save_quiz_score(
    request: Request,
    topic_id: int = Form(...),
    score: int = Form(...),
    total_questions: int = Form(...)
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    if (
        total_questions <= 0
        or score < 0
        or score > total_questions
    ):
        return {
            "success": False,
        "message": "Invalid quiz score."
    }

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
        ).first()

        if not topic:
            return {
                "success": False,
                "message": "Topic not found."
            }

        db.execute(
            text("""
                INSERT INTO quiz_attempts (
                    user_id,
                    topic_id,
                    score,
                    total_questions
                )
                VALUES (
                    :user_id,
                    :topic_id,
                    :score,
                    :total_questions
                )
            """),
            {
                "user_id": user_id,
                "topic_id": topic_id,
                "score": score,
                "total_questions": total_questions
            }
        )

        db.commit()

        return {
            "success": True,
            "message": "Quiz score saved successfully."
        }

    except Exception as e:

        db.rollback()

        print("Quiz score saving error:", repr(e))

        return {
            "success": False,
            "message": "Unable to save quiz score."
        }

    finally:
        db.close()