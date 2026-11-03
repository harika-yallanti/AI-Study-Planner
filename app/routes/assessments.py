from app.services.code_executor import execute_python
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text

from app.database import SessionLocal
import traceback

import json
import os

from dotenv import load_dotenv
from groq import Groq


assessments_router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

load_dotenv()

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
GROQ_MODEL = "openai/gpt-oss-20b"


# ASSESSMENTS LANDING PAGE

@assessments_router.get("/assessments")
def assessments_home(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        theory_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_exams
                WHERE user_id = :user_id
                  AND exam_type = 'theory'
            """),
            {"user_id": user_id}
        ).scalar() or 0

        practical_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_exams
                WHERE user_id = :user_id
                  AND exam_type = 'practical'
            """),
            {"user_id": user_id}
        ).scalar() or 0

        return templates.TemplateResponse(
            request=request,
            name="assessments.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "theory_count": theory_count,
                "practical_count": practical_count
            }
        )

    finally:
        db.close()


# THEORY ASSESSMENTS PAGE

@assessments_router.get("/assessments/theory")
def theory_assessments(request: Request):

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
        ).mappings().all()

        return templates.TemplateResponse(
            request=request,
            name="theory_assessments.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "subjects": [dict(subject) for subject in subjects]
            }
        )

    finally:
        db.close()
        
# PRACTICAL ASSESSMENTS PAGE
@assessments_router.get("/assessments/practical")
def practical_assessments(request: Request):

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
        ).mappings().all()

        practical_exams = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.creation_mode,
                    ae.duration_minutes,
                    ae.total_marks,
                    ae.question_count,
                    ae.status,
                    ae.created_at,
                    s.subject_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                WHERE ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
                ORDER BY ae.created_at DESC, ae.id DESC
            """),
            {"user_id": user_id}
        ).mappings().all()

        return templates.TemplateResponse(
            request=request,
            name="practical_assessment.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "subjects": [dict(subject) for subject in subjects],
                "practical_exams": [dict(exam) for exam in practical_exams]
            }
        )

    except Exception as error:
        print("Practical assessments page error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load practical assessments."},
            status_code=500
        )

    finally:
        db.close()


# LOAD TOPICS FOR A PRACTICAL ASSESSMENT

@assessments_router.get("/assessments/practical/topics/{subject_id}")
def get_practical_topics(request: Request, subject_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

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
            return JSONResponse(
                {"success": False, "message": "Subject not found."},
                status_code=404
            )

        topics = db.execute(
            text("""
                SELECT id, topic_name
                FROM topics
                WHERE subject_id = :subject_id
                ORDER BY topic_name
            """),
            {"subject_id": subject_id}
        ).mappings().all()

        return {
            "success": True,
            "topics": [dict(topic) for topic in topics]
        }

    finally:
        db.close()


# PRACTICAL ASSESSMENT CREATION PAGE

@assessments_router.get("/assessments/practical/create")
def create_practical_assessment(request: Request):

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
        ).mappings().all()

        return templates.TemplateResponse(
            request=request,
            name="practical_create.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "subjects": [dict(subject) for subject in subjects]
            }
        )

    finally:
        db.close()


# PRACTICAL ASSESSMENT CONFIGURATION PAGE

@assessments_router.get("/assessments/practical/configure")
def configure_practical_assessment(
    request: Request,
    subject_id: int,
    topic_id: int,
    mode: str
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if mode not in ["ai", "manual"]:
        return JSONResponse(
            {"detail": "Invalid creation mode."},
            status_code=400
        )

    db = SessionLocal()

    try:
        selected_data = db.execute(
            text("""
                SELECT
                    s.id AS subject_id,
                    s.subject_name,
                    t.id AS topic_id,
                    t.topic_name
                FROM subjects s
                JOIN topics t ON t.subject_id = s.id
                WHERE s.id = :subject_id
                  AND t.id = :topic_id
                  AND s.user_id = :user_id
            """),
            {
                "subject_id": subject_id,
                "topic_id": topic_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not selected_data:
            return JSONResponse(
                {"detail": "Selected subject or topic was not found."},
                status_code=404
            )

        return templates.TemplateResponse(
            request=request,
            name="practical_configure.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "selected": dict(selected_data),
                "mode": mode
            }
        )

    except Exception as error:
        print("Practical configuration error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load practical configuration."},
            status_code=500
        )

    finally:
        db.close()


# PRACTICAL ASSESSMENT QUESTION SETUP PAGE

@assessments_router.get("/assessments/practical/questions/setup")
def practical_questions_setup(
    request: Request,
    subject_id: int,
    topic_id: int,
    mode: str,
    title: str,
    duration: int,
    question_count: int,
    marks_per_question: int
):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if mode not in ["ai", "manual"]:
        return JSONResponse(
            {"detail": "Invalid creation mode."},
            status_code=400
        )

    title = title.strip()

    if not title or len(title) > 150:
        return JSONResponse(
            {"detail": "Assessment title must be between 1 and 150 characters."},
            status_code=400
        )

    if not (5 <= duration <= 300):
        return JSONResponse(
            {"detail": "Duration must be between 5 and 300 minutes."},
            status_code=400
        )

    if not (1 <= question_count <= 20):
        return JSONResponse(
            {"detail": "Question count must be between 1 and 20."},
            status_code=400
        )

    if not (1 <= marks_per_question <= 100):
        return JSONResponse(
            {"detail": "Marks per question must be between 1 and 100."},
            status_code=400
        )

    db = SessionLocal()

    try:
        selected = db.execute(
            text("""
                SELECT
                    s.id AS subject_id,
                    s.subject_name,
                    t.id AS topic_id,
                    t.topic_name
                FROM subjects s
                JOIN topics t ON t.subject_id = s.id
                WHERE s.id = :subject_id
                  AND t.id = :topic_id
                  AND s.user_id = :user_id
            """),
            {
                "subject_id": subject_id,
                "topic_id": topic_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not selected:
            return JSONResponse(
                {"detail": "Selected subject or topic was not found."},
                status_code=404
            )

        total_marks = question_count * marks_per_question

        return templates.TemplateResponse(
            request=request,
            name="practical_questions_setup.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "selected": dict(selected),
                "mode": mode,
                "title": title,
                "duration": duration,
                "question_count": question_count,
                "marks_per_question": marks_per_question,
                "total_marks": total_marks
            }
        )

    except Exception as error:
        print("Practical question setup error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load question setup."},
            status_code=500
        )

    finally:
        db.close()


# SAVE PRACTICAL ASSESSMENT CONFIGURATION

@assessments_router.post("/assessments/practical/save")
async def save_practical_assessment(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        form = await request.form()

        subject_id = int(form.get("subject_id", 0))
        topic_id = int(form.get("topic_id", 0))
        mode = str(form.get("mode", "")).strip()
        title = str(form.get("title", "")).strip()

        duration = int(form.get("duration", 0))
        question_count = int(form.get("question_count", 0))
        marks_per_question = int(form.get("marks_per_question", 0))

        if mode != "ai":
            return JSONResponse(
                {"detail": "This route currently supports AI creation only."},
                status_code=400
            )

        if not title or len(title) > 150:
            return JSONResponse(
                {"detail": "Enter a valid assessment title."},
                status_code=400
            )

        if not (5 <= duration <= 300):
            return JSONResponse(
                {"detail": "Duration must be between 5 and 300 minutes."},
                status_code=400
            )

        if not (1 <= question_count <= 20):
            return JSONResponse(
                {"detail": "Question count must be between 1 and 20."},
                status_code=400
            )

        if not (1 <= marks_per_question <= 100):
            return JSONResponse(
                {"detail": "Marks per question must be between 1 and 100."},
                status_code=400
            )

        selected = db.execute(
            text("""
                SELECT s.id, t.id AS topic_id
                FROM subjects s
                JOIN topics t ON t.subject_id = s.id
                WHERE s.id = :subject_id
                  AND t.id = :topic_id
                  AND s.user_id = :user_id
            """),
            {
                "subject_id": subject_id,
                "topic_id": topic_id,
                "user_id": user_id
            }
        ).first()

        if not selected:
            return JSONResponse(
                {"detail": "Invalid subject or topic selection."},
                status_code=404
            )

        total_marks = question_count * marks_per_question

        result = db.execute(
            text("""
                INSERT INTO assessment_exams (
                    user_id,
                    subject_id,
                    topic_id,
                    exam_title,
                    exam_type,
                    creation_mode,
                    duration_minutes,
                    total_marks,
                    status,
                    question_count,
                    marks_per_question,
                    question_types
                )
                VALUES (
                    :user_id,
                    :subject_id,
                    :topic_id,
                    :exam_title,
                    'practical',
                    'ai',
                    :duration_minutes,
                    :total_marks,
                    'draft',
                    :question_count,
                    :marks_per_question,
                    :question_types
                )
            """),
            {
                "user_id": user_id,
                "subject_id": subject_id,
                "topic_id": topic_id,
                "exam_title": title,
                "duration_minutes": duration,
                "total_marks": total_marks,
                "question_count": question_count,
                "marks_per_question": marks_per_question,
                "question_types": json.dumps(["programming"])
            }
        )

        exam_id = result.lastrowid
        db.commit()

        return RedirectResponse(
            url=f"/assessments/practical/questions/{exam_id}",
            status_code=303
        )

    except (ValueError, TypeError):
        db.rollback()
        return JSONResponse(
            {"detail": "Invalid assessment configuration values."},
            status_code=400
        )

    except Exception as error:
        db.rollback()
        print("Save practical assessment error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to save practical assessment."},
            status_code=500
        )

    finally:
        db.close()


# PRACTICAL ASSESSMENT QUESTION GENERATION PAGE

@assessments_router.get("/assessments/practical/questions/{exam_id}")
def practical_questions_page(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.*,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                LEFT JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"detail": "Practical assessment not found."},
                status_code=404
            )

        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_text,
                    programming_language,
                    starter_code,
                    test_cases,
                    marks,
                    question_order
                FROM assessment_questions
                WHERE exam_id = :exam_id
                ORDER BY question_order, id
            """),
            {"exam_id": exam_id}
        ).mappings().all()

        return templates.TemplateResponse(
            request=request,
            name="practical_questions.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "exam": dict(exam),
                "questions": [dict(question) for question in questions]
            }
        )

    except Exception as error:
        print("Practical questions page error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load practical questions."},
            status_code=500
        )

    finally:
        db.close()


# GENERATE PYTHON PRACTICAL QUESTIONS USING GROQ

@assessments_router.post("/assessments/practical/generate/{exam_id}")
def generate_practical_questions(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"detail": "Please log in again."},
            status_code=401
        )

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.*,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                LEFT JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND ae.creation_mode = 'ai'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"detail": "Practical assessment not found."},
                status_code=404
            )

        existing_questions = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_questions
                WHERE exam_id = :exam_id
            """),
            {"exam_id": exam_id}
        ).scalar()

        if existing_questions:
            return JSONResponse(
                {
                    "detail": "Questions have already been generated. "
                              "Please review the existing questions."
                },
                status_code=409
            )

        prompt = f"""
You are an experienced Python programming instructor.

Create exactly {exam.question_count} Python programming questions
for a student practical assessment.

ASSESSMENT DETAILS:
Subject: {exam.subject_name}
Topic: {exam.topic_name or "General"}
Assessment title: {exam.exam_title}
Programming language: Python
Marks per question: {exam.marks_per_question}

REQUIREMENTS:
1. Generate exactly {exam.question_count} distinct programming problems.
2. Questions must be relevant to the selected topic.
3. Use Python only.
4. Each question must contain a clear problem statement.
5. Include starter Python code.
6. Include at least 3 test cases per question.
7. Test cases must include input and expected output.
8. Include normal and edge cases where appropriate.
9. Do not include multiple-choice questions.
10. Do not include the complete solution in starter_code.
11. Keep the difficulty appropriate for a college student.
12. Assign exactly {exam.marks_per_question} marks to each question.

Return ONLY valid JSON using this exact structure:

{{
    "questions": [
        {{
            "question_text": "Problem statement",
            "programming_language": "python",
            "starter_code": "# Write your Python solution here",
            "test_cases": [
                {{
                    "input": "sample input",
                    "expected_output": "sample output"
                }},
                {{
                    "input": "sample input",
                    "expected_output": "sample output"
                }},
                {{
                    "input": "sample input",
                    "expected_output": "sample output"
                }}
            ],
            "marks": {exam.marks_per_question}
        }}
    ]
}}

Do not add Markdown code fences or explanations outside the JSON.
"""

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "You generate accurate Python programming "
                               "assessments and return valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.4,
            max_completion_tokens=6000
        )

        ai_content = response.choices[0].message.content.strip()

        # Remove Markdown fences if the model returns them.
        if ai_content.startswith("```"):
            ai_content = ai_content.split("\n", 1)[1]
            ai_content = ai_content.rsplit("```", 1)[0].strip()

        generated_data = json.loads(ai_content)
        generated_questions = generated_data.get("questions")

        if not isinstance(generated_questions, list):
            raise ValueError("AI response does not contain a valid questions list.")

        if len(generated_questions) != exam.question_count:
            raise ValueError("AI generated an incorrect number of questions.")

        prepared_questions = []

        for index, question in enumerate(generated_questions, start=1):

            question_text = question.get("question_text")
            starter_code = question.get("starter_code")
            language = str(
                question.get("programming_language", "")
            ).strip().lower()
            test_cases = question.get("test_cases")
            marks = question.get("marks")

            if not isinstance(question_text, str) or not question_text.strip():
                raise ValueError(f"Question {index} has no valid problem statement.")

            if not isinstance(starter_code, str):
                raise ValueError(f"Question {index} has invalid starter code.")

            if language != "python":
                raise ValueError(f"Question {index} is not a Python question.")

            if not isinstance(test_cases, list) or len(test_cases) < 3:
                raise ValueError(f"Question {index} must have at least 3 test cases.")

            for test_case in test_cases:
                if (
                    not isinstance(test_case, dict)
                    or not isinstance(test_case.get("input"), str)
                    or not isinstance(test_case.get("expected_output"), str)
                ):
                    raise ValueError(
                        f"Question {index} contains an invalid test case."
                    )

            if isinstance(marks, bool) or marks != exam.marks_per_question:
                raise ValueError(f"Question {index} has an incorrect marks value.")

            prepared_questions.append({
                "exam_id": exam_id,
                "question_text": question_text.strip(),
                "programming_language": "python",
                "starter_code": starter_code,
                "test_cases": json.dumps(test_cases),
                "marks": exam.marks_per_question,
                "question_order": index
            })

        for question in prepared_questions:
            db.execute(
                text("""
                    INSERT INTO assessment_questions (
                        exam_id,
                        question_type,
                        question_text,
                        programming_language,
                        starter_code,
                        test_cases,
                        marks,
                        question_order
                    )
                    VALUES (
                        :exam_id,
                        'programming',
                        :question_text,
                        :programming_language,
                        :starter_code,
                        :test_cases,
                        :marks,
                        :question_order
                    )
                """),
                question
            )

        db.commit()

        return JSONResponse({
            "success": True,
            "message": "Python programming questions generated successfully.",
            "exam_id": exam_id,
            "question_count": len(prepared_questions)
        })

    except json.JSONDecodeError:
        db.rollback()
        print("Groq returned invalid JSON.")
        return JSONResponse(
            {"detail": "AI returned an invalid response. Please try again."},
            status_code=502
        )

    except Exception as error:
        db.rollback()
        print("Practical AI generation error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to generate practical questions. Please try again."},
            status_code=500
        )

    finally:
        db.close()


# PRACTICAL ASSESSMENT REVIEW PAGE

@assessments_router.get("/assessments/practical/review/{exam_id}")
def practical_assessment_review(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.*,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                LEFT JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
            """),
            {"exam_id": exam_id, "user_id": user_id}
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"detail": "Practical assessment not found."},
                status_code=404
            )

        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_text,
                    programming_language,
                    starter_code,
                    test_cases,
                    marks,
                    question_order
                FROM assessment_questions
                WHERE exam_id = :exam_id
                  AND question_type = 'programming'
                ORDER BY question_order, id
            """),
            {"exam_id": exam_id}
        ).mappings().all()

        prepared_questions = []

        for question in questions:
            question_data = dict(question)

            try:
                question_data["test_cases_data"] = json.loads(
                    question_data["test_cases"] or "[]"
                )
            except (json.JSONDecodeError, TypeError):
                question_data["test_cases_data"] = []

            prepared_questions.append(question_data)

        return templates.TemplateResponse(
            request=request,
            name="practical_review.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "exam": dict(exam),
                "questions": prepared_questions
            }
        )

    except Exception as error:
        print("Practical review page error:", error)
        traceback.print_exc()
        return JSONResponse(
            {"detail": "Unable to load assessment review."},
            status_code=500
        )

    finally:
        db.close()


# UPDATE A PRACTICAL QUESTION

@assessments_router.post("/assessments/practical/question/update/{question_id}")
async def update_practical_question(request: Request, question_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        form = await request.form()

        question_text = str(form.get("question_text", "")).strip()
        starter_code = str(form.get("starter_code", ""))
        test_cases_text = str(form.get("test_cases", ""))
        marks = int(form.get("marks", 0))

        if not question_text or len(question_text) > 10000:
            return JSONResponse(
                {"detail": "Enter a valid question statement."},
                status_code=400
            )

        if len(starter_code) > 20000:
            return JSONResponse(
                {"detail": "Starter code is too long."},
                status_code=400
            )

        if not (1 <= marks <= 100):
            return JSONResponse(
                {"detail": "Marks must be between 1 and 100."},
                status_code=400
            )

        test_cases = json.loads(test_cases_text)

        if not isinstance(test_cases, list) or len(test_cases) < 3:
            return JSONResponse(
                {"detail": "At least 3 test cases are required."},
                status_code=400
            )

        for case in test_cases:
            if (
                not isinstance(case, dict)
                or not isinstance(case.get("input"), str)
                or not isinstance(case.get("expected_output"), str)
            ):
                return JSONResponse(
                    {"detail": "Each test case needs input and expected_output text."},
                    status_code=400
                )

        question = db.execute(
            text("""
                SELECT aq.id, aq.exam_id, ae.total_marks
                FROM assessment_questions aq
                JOIN assessment_exams ae ON ae.id = aq.exam_id
                WHERE aq.id = :question_id
                  AND aq.question_type = 'programming'
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'draft'
            """),
            {"question_id": question_id, "user_id": user_id}
        ).mappings().first()

        if not question:
            return JSONResponse(
                {"detail": "Editable draft question not found."},
                status_code=404
            )

        question_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_questions
                WHERE exam_id = :exam_id
                  AND question_type = 'programming'
            """),
            {"exam_id": question["exam_id"]}
        ).scalar()

        exam = db.execute(
            text("""
                SELECT question_count, marks_per_question
                FROM assessment_exams
                WHERE id = :exam_id
            """),
            {"exam_id": question["exam_id"]}
        ).mappings().first()

        if marks != exam["marks_per_question"]:
            return JSONResponse(
                {
                    "detail": "Each question must have "
                              "the configured marks per question."
                },
                status_code=400
            )

        db.execute(
            text("""
                UPDATE assessment_questions
                SET question_text = :question_text,
                    starter_code = :starter_code,
                    test_cases = :test_cases,
                    marks = :marks
                WHERE id = :question_id
            """),
            {
                "question_text": question_text,
                "starter_code": starter_code,
                "test_cases": json.dumps(test_cases),
                "marks": marks,
                "question_id": question_id
            }
        )

        db.commit()

        return RedirectResponse(
            url=f"/assessments/practical/review/{question['exam_id']}",
            status_code=303
        )

    except (ValueError, TypeError, json.JSONDecodeError):
        db.rollback()
        return JSONResponse(
            {"detail": "Invalid marks or test-case JSON."},
            status_code=400
        )

    except Exception as error:
        db.rollback()
        print("Update practical question error:", error)
        traceback.print_exc()
        return JSONResponse(
            {"detail": "Unable to update question."},
            status_code=500
        )

    finally:
        db.close()


# DELETE A PRACTICAL QUESTION

@assessments_router.post("/assessments/practical/question/delete/{question_id}")
def delete_practical_question(request: Request, question_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        question = db.execute(
            text("""
                SELECT aq.id, aq.exam_id
                FROM assessment_questions aq
                JOIN assessment_exams ae ON ae.id = aq.exam_id
                WHERE aq.id = :question_id
                  AND aq.question_type = 'programming'
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'draft'
            """),
            {"question_id": question_id, "user_id": user_id}
        ).mappings().first()

        if not question:
            return JSONResponse(
                {"detail": "Editable draft question not found."},
                status_code=404
            )

        db.execute(
            text("""
                DELETE FROM assessment_questions
                WHERE id = :question_id
            """),
            {"question_id": question_id}
        )

        db.commit()

        return RedirectResponse(
            url=f"/assessments/practical/review/{question['exam_id']}",
            status_code=303
        )

    except Exception as error:
        db.rollback()
        print("Delete practical question error:", error)
        traceback.print_exc()
        return JSONResponse(
            {"detail": "Unable to delete question."},
            status_code=500
        )

    finally:
        db.close()


# PUBLISH PRACTICAL ASSESSMENT

@assessments_router.post("/assessments/practical/publish/{exam_id}")
def publish_practical_assessment(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT id, question_count, marks_per_question, status
                FROM assessment_exams
                WHERE id = :exam_id
                  AND user_id = :user_id
                  AND exam_type = 'practical'
            """),
            {"exam_id": exam_id, "user_id": user_id}
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"detail": "Practical assessment not found."},
                status_code=404
            )

        if exam["status"] != "draft":
            return JSONResponse(
                {"detail": "Only draft assessments can be published."},
                status_code=400
            )

        questions = db.execute(
            text("""
                SELECT id, marks, test_cases
                FROM assessment_questions
                WHERE exam_id = :exam_id
                  AND question_type = 'programming'
                ORDER BY question_order, id
            """),
            {"exam_id": exam_id}
        ).mappings().all()

        if len(questions) != exam["question_count"]:
            return JSONResponse(
                {
                    "detail": (
                        f"Expected {exam['question_count']} questions, "
                        f"but found {len(questions)}. "
                        "Add or regenerate questions before publishing."
                    )
                },
                status_code=400
            )

        for question in questions:
            if question["marks"] != exam["marks_per_question"]:
                return JSONResponse(
                    {"detail": "A question has an incorrect marks value."},
                    status_code=400
                )

            try:
                cases = json.loads(question["test_cases"] or "[]")
            except (json.JSONDecodeError, TypeError):
                cases = []

            if not isinstance(cases, list) or len(cases) < 3:
                return JSONResponse(
                    {"detail": "Every question needs at least 3 valid test cases."},
                    status_code=400
                )

            for case in cases:
                if (
                    not isinstance(case, dict)
                    or not isinstance(case.get("input"), str)
                    or not isinstance(case.get("expected_output"), str)
                ):
                    return JSONResponse(
                        {"detail": "A question contains an invalid test case."},
                        status_code=400
                    )

        db.execute(
            text("""
                UPDATE assessment_exams
                SET status = 'published'
                WHERE id = :exam_id
                  AND user_id = :user_id
            """),
            {"exam_id": exam_id, "user_id": user_id}
        )

        db.commit()

        return RedirectResponse(
            url=f"/assessments/practical/review/{exam_id}",
            status_code=303
        )

    except Exception as error:
        db.rollback()
        print("Publish practical assessment error:", error)
        traceback.print_exc()
        return JSONResponse(
            {"detail": "Unable to publish practical assessment."},
            status_code=500
        )

    finally:
        db.close()


# STUDENT: VIEW PUBLISHED PRACTICAL ASSESSMENTS

@assessments_router.get("/assessments/practical/available")
def available_practical_assessments(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        assessments = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.duration_minutes,
                    ae.total_marks,
                    ae.question_count,
                    ae.created_at,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s
                    ON s.id = ae.subject_id
                LEFT JOIN topics t
                    ON t.id = ae.topic_id
                WHERE ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'published'
                ORDER BY ae.created_at DESC
            """),
            {"user_id": user_id}
        ).mappings().all()

        return templates.TemplateResponse(
            request=request,
            name="practical_available.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "assessments": [dict(item) for item in assessments]
            }
        )

    except Exception as error:
        print("Available practical assessments error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load practical assessments."},
            status_code=500
        )

    finally:
        db.close()


# STUDENT: PRACTICAL ASSESSMENT INSTRUCTIONS

@assessments_router.get("/assessments/practical/instructions/{exam_id}")
def practical_assessment_instructions(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.duration_minutes,
                    ae.total_marks,
                    ae.question_count,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                LEFT JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'published'
            """),
            {"exam_id": exam_id, "user_id": user_id}
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"detail": "Published practical assessment not found."},
                status_code=404
            )

        return templates.TemplateResponse(
            request=request,
            name="practical_instructions.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "exam": dict(exam)
            }
        )

    except Exception as error:
        print("Practical instructions error:", error)
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load assessment instructions."},
            status_code=500
        )

    finally:
        db.close()


# LOAD TOPICS FOR A SELECTED SUBJECT

@assessments_router.get("/assessments/theory/topics/{subject_id}")
def get_theory_topics(request: Request, subject_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

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
            return JSONResponse(
                {"success": False, "message": "Subject not found."},
                status_code=404
            )

        topics = db.execute(
            text("""
                SELECT id, topic_name
                FROM topics
                WHERE subject_id = :subject_id
                ORDER BY topic_name
            """),
            {"subject_id": subject_id}
        ).mappings().all()

        return {
            "success": True,
            "topics": [dict(topic) for topic in topics]
        }

    finally:
        db.close()


# THEORY ASSESSMENT CREATION PAGE

@assessments_router.get("/assessments/theory/create")
def create_theory_assessment(
    request: Request,
    subject_id: int,
    topic_id: int,
    mode: str
):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    if mode not in ["ai", "manual"]:
        return RedirectResponse(
            url="/assessments/theory",
            status_code=303
        )

    db = SessionLocal()

    try:
        selected = db.execute(
            text("""
                SELECT
                    subjects.id AS subject_id,
                    subjects.subject_name,
                    topics.id AS topic_id,
                    topics.topic_name
                FROM subjects
                JOIN topics
                    ON topics.subject_id = subjects.id
                WHERE subjects.id = :subject_id
                  AND topics.id = :topic_id
                  AND subjects.user_id = :user_id
            """),
            {
                "subject_id": subject_id,
                "topic_id": topic_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not selected:
            return RedirectResponse(
                url="/assessments/theory",
                status_code=303
            )

        return templates.TemplateResponse(
            request=request,
            name="theory_create.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "subject": dict(selected),
                "mode": mode
            }
        )

    finally:
        db.close()


# SAVE THEORY ASSESSMENT CONFIGURATION

@assessments_router.post("/assessments/theory/save")
async def save_theory_assessment(request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

    try:
        data = await request.json()

        title = str(data.get("exam_title", "")).strip()
        subject_id = int(data.get("subject_id"))
        topic_id = int(data.get("topic_id"))
        duration = int(data.get("duration_minutes"))
        question_count = int(data.get("question_count"))
        marks_per_question = int(data.get("marks_per_question"))
        mode = data.get("mode")
        question_types = data.get("question_types")

        if not title or len(title) > 200:
            raise ValueError("Enter a valid assessment title.")

        if duration < 5 or duration > 300:
            raise ValueError("Duration must be between 5 and 300 minutes.")

        if question_count < 1 or question_count > 30:
            raise ValueError("Question count must be between 1 and 30.")

        if marks_per_question < 1 or marks_per_question > 20:
            raise ValueError("Marks per question must be between 1 and 20.")

        if mode not in ["ai", "manual"]:
            raise ValueError("Invalid assessment creation mode.")

        if (
            not isinstance(question_types, list)
            or not question_types
            or any(
                item not in ["mcq", "descriptive"]
                for item in question_types
            )
        ):
            raise ValueError("Select at least one valid question type.")

        db = SessionLocal()

        try:
            selected = db.execute(
                text("""
                    SELECT subjects.id
                    FROM subjects
                    JOIN topics
                        ON topics.subject_id = subjects.id
                    WHERE subjects.id = :subject_id
                      AND topics.id = :topic_id
                      AND subjects.user_id = :user_id
                """),
                {
                    "subject_id": subject_id,
                    "topic_id": topic_id,
                    "user_id": user_id
                }
            ).first()

            if not selected:
                return JSONResponse(
                    {
                        "success": False,
                        "message": "Invalid subject or topic."
                    },
                    status_code=403
                )

            total_marks = question_count * marks_per_question

            result = db.execute(
                text("""
                    INSERT INTO assessment_exams (
                        user_id,
                        subject_id,
                        topic_id,
                        exam_title,
                        exam_type,
                        creation_mode,
                        duration_minutes,
                        total_marks,
                        question_count,
                        marks_per_question,
                        question_types,
                        status
                    )
                    VALUES (
                        :user_id,
                        :subject_id,
                        :topic_id,
                        :exam_title,
                        'theory',
                        :creation_mode,
                        :duration_minutes,
                        :total_marks,
                        :question_count,
                        :marks_per_question,
                        :question_types,
                        'draft'
                    )
                """),
                {
                    "user_id": user_id,
                    "subject_id": subject_id,
                    "topic_id": topic_id,
                    "exam_title": title,
                    "creation_mode": mode,
                    "duration_minutes": duration,
                    "total_marks": total_marks,
                    "question_count": question_count,
                    "marks_per_question": marks_per_question,
                    "question_types": json.dumps(question_types)
                }
            )

            exam_id = result.lastrowid
            db.commit()

            return JSONResponse({
                "success": True,
                "message": "Assessment configuration saved successfully.",
                "exam_id": exam_id
            })

        except Exception:
            db.rollback()
            raise

        finally:
            db.close()

    except (ValueError, TypeError):
        return JSONResponse(
            {
                "success": False,
                "message": "Please check the assessment details."
            },
            status_code=400
        )

    except Exception as error:
        print("Assessment save error:", error)

        return JSONResponse(
            {
                "success": False,
                "message": "Unable to save the assessment. Please try again."
            },
            status_code=500
        )


# THEORY QUESTIONS SETUP PAGE

@assessments_router.get("/assessments/theory/questions/{exam_id}")
def theory_questions_setup(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.exam_type,
                    ae.creation_mode,
                    ae.duration_minutes,
                    ae.total_marks,
                    ae.question_count,
                    ae.status,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                LEFT JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'theory'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return RedirectResponse(
                url="/assessments/theory",
                status_code=303
            )

        question_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_questions
                WHERE exam_id = :exam_id
            """),
            {"exam_id": exam_id}
        ).scalar() or 0

        return templates.TemplateResponse(
            request=request,
            name="theory_questions.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "exam": exam,
                "question_count": question_count
            }
        )

    finally:
        db.close()


# GENERATE THEORY QUESTIONS USING GROQ

@assessments_router.post("/assessments/theory/generate/{exam_id}")
async def generate_theory_questions(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.subject_id,
                    ae.topic_id,
                    ae.question_count,
                    ae.marks_per_question,
                    ae.question_types,
                    ae.status,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'theory'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"success": False, "message": "Assessment not found."},
                status_code=404
            )

        if exam["status"] != "draft":
            return JSONResponse(
                {
                    "success": False,
                    "message": "Only draft assessments can generate questions."
                },
                status_code=400
            )

        existing_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_questions
                WHERE exam_id = :exam_id
            """),
            {"exam_id": exam_id}
        ).scalar() or 0

        if existing_count > 0:
            return JSONResponse(
                {
                    "success": False,
                    "message": (
                        "Questions already exist for this assessment. "
                        "They have not been replaced."
                    )
                },
                status_code=409
            )

        question_types = exam["question_types"]

        if isinstance(question_types, str):
            question_types = json.loads(question_types)

        if not isinstance(question_types, list) or not question_types:
            return JSONResponse(
                {
                    "success": False,
                    "message": "No valid question types were configured."
                },
                status_code=400
            )

        question_count = int(exam["question_count"])
        marks_per_question = int(exam["marks_per_question"])

        prompt = f"""
You are an experienced university examination question setter.

Create exactly {question_count} theory assessment questions.

Subject: {exam['subject_name']}
Topic: {exam['topic_name']}
Assessment title: {exam['exam_title']}

Allowed question types: {json.dumps(question_types)}
Marks per question: {marks_per_question}

Requirements:
1. Generate exactly {question_count} questions.
2. Use only the allowed question types.
3. Distribute selected question types as evenly as possible.
4. Questions must be relevant to the given subject and topic.
5. Use clear, student-friendly academic language.
6. MCQ questions must have exactly four options.
7. Each MCQ must have one unambiguous correct answer.
8. Descriptive questions must include a reference answer.
9. Do not include answers in the question text.

Return only valid JSON in this format:

{{
  "questions": [
    {{
      "question_type": "mcq",
      "question_text": "Question text",
      "options": [
        "Option A",
        "Option B",
        "Option C",
        "Option D"
      ],
      "correct_answer": "Exact correct option text",
      "expected_answer": null,
      "explanation": "Brief explanation"
    }},
    {{
      "question_type": "descriptive",
      "question_text": "Question text",
      "options": null,
      "correct_answer": null,
      "expected_answer": "Detailed reference answer",
      "explanation": "Key points expected in the answer"
    }}
  ]
}}
"""

        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate accurate examination questions "
                        "and return valid JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={"type": "json_object"},
            temperature=0.4
        )

        generated_data = json.loads(
            response.choices[0].message.content
        )

        questions = generated_data.get("questions")

        if not isinstance(questions, list) or len(questions) != question_count:
            raise ValueError(
                "The AI did not generate the required number of questions."
            )

        allowed_types = set(question_types)
        validated_questions = []

        for index, question in enumerate(questions, start=1):

            if not isinstance(question, dict):
                raise ValueError("The AI returned an invalid question.")

            question_type = question.get("question_type")
            question_text = str(
                question.get("question_text") or ""
            ).strip()

            if question_type not in allowed_types:
                raise ValueError(
                    "The AI returned an unsupported question type."
                )

            if question_type not in ["mcq", "descriptive"] or not question_text:
                raise ValueError("The AI returned an invalid question.")

            options = question.get("options")
            correct_answer = question.get("correct_answer")
            expected_answer = question.get("expected_answer")
            explanation = question.get("explanation")

            if question_type == "mcq":

                if not isinstance(options, list) or len(options) != 4:
                    raise ValueError(
                        "An MCQ must contain exactly four options."
                    )

                options = [
                    str(option).strip()
                    for option in options
                ]

                if any(not option for option in options):
                    raise ValueError("An MCQ contains an empty option.")

                if (
                    not correct_answer
                    or str(correct_answer).strip() not in options
                ):
                    raise ValueError(
                        "An MCQ has an invalid correct answer."
                    )

                correct_answer = str(correct_answer).strip()
                expected_answer = None

            else:
                options = None
                correct_answer = None

                if (
                    not expected_answer
                    or not str(expected_answer).strip()
                ):
                    raise ValueError(
                        "A descriptive question is missing its reference answer."
                    )

                expected_answer = str(expected_answer).strip()

            validated_questions.append({
                "exam_id": exam_id,
                "question_type": question_type,
                "question_text": question_text,
                "options": (
                    json.dumps(options)
                    if options is not None
                    else None
                ),
                "correct_answer": correct_answer,
                "expected_answer": expected_answer,
                "explanation": str(explanation or "").strip(),
                "marks": marks_per_question,
                "question_order": index
            })

        for question in validated_questions:
            db.execute(
                text("""
                    INSERT INTO assessment_questions (
                        exam_id,
                        question_type,
                        question_text,
                        options,
                        correct_answer,
                        expected_answer,
                        explanation,
                        marks,
                        question_order
                    )
                    VALUES (
                        :exam_id,
                        :question_type,
                        :question_text,
                        :options,
                        :correct_answer,
                        :expected_answer,
                        :explanation,
                        :marks,
                        :question_order
                    )
                """),
                question
            )

        db.commit()

        return JSONResponse({
            "success": True,
            "message": "AI questions generated and saved successfully.",
            "exam_id": exam_id,
            "question_count": len(validated_questions)
        })

    except (ValueError, TypeError, json.JSONDecodeError) as error:
        db.rollback()
        print("Assessment generation validation error:", error)

        return JSONResponse(
            {"success": False, "message": str(error)},
            status_code=422
        )

    except Exception as error:
        db.rollback()
        print("Assessment generation error:", error)

        return JSONResponse(
            {
                "success": False,
                "message": "Unable to generate questions. Please try again."
            },
            status_code=500
        )

    finally:
        db.close()


# REVIEW THEORY ASSESSMENT

@assessments_router.get("/assessments/theory/review/{exam_id}")
def review_theory_assessment(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.duration_minutes,
                    ae.total_marks,
                    ae.question_count,
                    ae.status,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'theory'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return RedirectResponse(
                url="/assessments",
                status_code=303
            )

        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_type,
                    question_text,
                    options,
                    correct_answer,
                    expected_answer,
                    explanation,
                    marks,
                    question_order
                FROM assessment_questions
                WHERE exam_id = :exam_id
                ORDER BY question_order
            """),
            {"exam_id": exam_id}
        ).mappings().all()

        question_list = []

        for question in questions:
            item = dict(question)

            if isinstance(item["options"], str):
                item["options"] = json.loads(item["options"])

            question_list.append(item)

        return templates.TemplateResponse(
            request=request,
            name="theory_questions_review.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "exam": exam,
                "questions": question_list
            }
        )

    finally:
        db.close()


# PUBLISH THEORY ASSESSMENT

@assessments_router.post("/assessments/theory/publish/{exam_id}")
def publish_theory_assessment(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT id, status, question_count
                FROM assessment_exams
                WHERE id = :exam_id
                  AND user_id = :user_id
                  AND exam_type = 'theory'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return RedirectResponse(
                url="/assessments",
                status_code=303
            )

        question_count = db.execute(
            text("""
                SELECT COUNT(*)
                FROM assessment_questions
                WHERE exam_id = :exam_id
            """),
            {"exam_id": exam_id}
        ).scalar() or 0

        if question_count != exam["question_count"]:
            return RedirectResponse(
                url=f"/assessments/theory/review/{exam_id}",
                status_code=303
            )

        db.execute(
            text("""
                UPDATE assessment_exams
                SET status = 'published'
                WHERE id = :exam_id
                  AND user_id = :user_id
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        )

        db.commit()

        return RedirectResponse(
            url=f"/assessments/theory/attempt/{exam_id}",
            status_code=303
        )

    except Exception as error:
        db.rollback()
        print("Assessment publishing error:", error)

        return RedirectResponse(
            url=f"/assessments/theory/review/{exam_id}",
            status_code=303
        )

    finally:
        db.close()


# THEORY ASSESSMENT ATTEMPT PAGE

@assessments_router.get("/assessments/theory/attempt/{exam_id}")
def theory_assessment_attempt(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        exam = db.execute(
            text("""
                SELECT
                    ae.id,
                    ae.exam_title,
                    ae.duration_minutes,
                    ae.total_marks,
                    ae.status,
                    s.subject_name,
                    t.topic_name
                FROM assessment_exams ae
                JOIN subjects s ON s.id = ae.subject_id
                LEFT JOIN topics t ON t.id = ae.topic_id
                WHERE ae.id = :exam_id
                  AND ae.user_id = :user_id
                  AND ae.exam_type = 'theory'
                  AND ae.status = 'published'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return RedirectResponse(
                url="/assessments",
                status_code=303
            )

        attempt = db.execute(
            text("""
                SELECT id, started_at, status
                FROM assessment_attempts
                WHERE exam_id = :exam_id
                  AND user_id = :user_id
                ORDER BY id DESC
                LIMIT 1
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if attempt and attempt["status"] != "in_progress":
            return RedirectResponse(
                url=f"/assessments/theory/results/{attempt['id']}",
                status_code=303
            )

        if not attempt:
            result = db.execute(
                text("""
                    INSERT INTO assessment_attempts (
                        exam_id,
                        user_id,
                        total_marks,
                        status
                    )
                    VALUES (
                        :exam_id,
                        :user_id,
                        :total_marks,
                        'in_progress'
                    )
                """),
                {
                    "exam_id": exam_id,
                    "user_id": user_id,
                    "total_marks": exam["total_marks"]
                }
            )

            attempt_id = result.lastrowid
            db.commit()

            attempt = {
                "id": attempt_id,
                "status": "in_progress"
            }

        remaining_seconds = db.execute(
            text("""
                SELECT GREATEST(
                    0,
                    (:duration_minutes * 60) -
                    TIMESTAMPDIFF(
                        SECOND,
                        started_at,
                        NOW()
                    )
                )
                FROM assessment_attempts
                WHERE id = :attempt_id
                  AND user_id = :user_id
            """),
            {
                "duration_minutes": exam["duration_minutes"],
                "attempt_id": attempt["id"],
                "user_id": user_id
            }
        ).scalar()

        if remaining_seconds is None:
            remaining_seconds = 0

        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_type,
                    question_text,
                    options,
                    marks,
                    question_order
                FROM assessment_questions
                WHERE exam_id = :exam_id
                ORDER BY question_order, id
            """),
            {"exam_id": exam_id}
        ).mappings().all()

        # Convert read-only SQLAlchemy rows into editable dictionaries
        questions = [
            dict(question)
            for question in questions
        ]

        for question in questions:
            if question["options"]:
                if isinstance(question["options"], str):
                    question["options"] = json.loads(
                        question["options"]
                    )

        return templates.TemplateResponse(
            request=request,
            name="theory_attempt.html",
            context={
                "user_name": request.session.get("user_name", "Student"),
                "user_role": request.session.get("user_role", "student"),
                "exam": exam,
                "questions": questions,
                "attempt_id": attempt["id"],
                "remaining_seconds": int(remaining_seconds)
            }
        )

    except Exception as error:
        db.rollback()
        print("Theory assessment attempt error:", error)
        raise

    finally:
        db.close()


# SUBMIT THEORY ASSESSMENT

@assessments_router.post("/assessments/theory/submit/{exam_id}")
async def submit_theory_assessment(request: Request, exam_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

    db = SessionLocal()

    try:
        data = await request.json()

        attempt_id = int(data.get("attempt_id"))
        answers = data.get("answers", {})

        if not isinstance(answers, dict):
            return JSONResponse(
                {"success": False, "message": "Invalid answer data."},
                status_code=400
            )

        # Verify assessment ownership and publication status
        exam = db.execute(
            text("""
                SELECT
                    id,
                    duration_minutes,
                    total_marks,
                    status
                FROM assessment_exams
                WHERE id = :exam_id
                  AND user_id = :user_id
                  AND exam_type = 'theory'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam or exam["status"] != "published":
            return JSONResponse(
                {"success": False, "message": "Assessment not found."},
                status_code=404
            )

        # Verify the exact attempt belongs to this student
        attempt = db.execute(
            text("""
                SELECT
                    id,
                    started_at,
                    status,
                    TIMESTAMPDIFF(
                        SECOND,
                        started_at,
                        NOW()
                    ) AS elapsed_seconds
                FROM assessment_attempts
                WHERE id = :attempt_id
                  AND exam_id = :exam_id
                  AND user_id = :user_id
            """),
            {
                "attempt_id": attempt_id,
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not attempt:
            return JSONResponse(
                {"success": False, "message": "Assessment attempt not found."},
                status_code=404
            )

        if attempt["status"] != "in_progress":
            return JSONResponse(
                {
                    "success": False,
                    "message": "This assessment has already been submitted."
                },
                status_code=409
            )

        # Enforce the timer on the server
        time_limit = int(exam["duration_minutes"]) * 60
        elapsed = int(attempt["elapsed_seconds"] or 0)

        if elapsed > time_limit + 30:
            return JSONResponse(
                {
                    "success": False,
                    "message": "The assessment time has expired. Please reload the assessment."
                },
                status_code=409
            )

        # Load the questions and their answer keys
        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_type,
                    question_text,
                    correct_answer,
                    expected_answer,
                    explanation,
                    marks
                FROM assessment_questions
                WHERE exam_id = :exam_id
                ORDER BY question_order, id
            """),
            {"exam_id": exam_id}
        ).mappings().all()

        if not questions:
            return JSONResponse(
                {"success": False, "message": "No questions found."},
                status_code=400
            )

        # Validate and prepare descriptive answers for AI evaluation
        descriptive_items = []

        for question in questions:
            answer = str(
                answers.get(str(question["id"]), "") or ""
            ).strip()

            if len(answer) > 10000:
                return JSONResponse(
                    {
                        "success": False,
                        "message": "An answer is too long. Please shorten it."
                    },
                    status_code=400
                )

            if question["question_type"] == "descriptive" and answer:
                descriptive_items.append({
                    "question_id": question["id"],
                    "question": question["question_text"],
                    "student_answer": answer,
                    "reference_answer": question["expected_answer"],
                    "key_points": question["explanation"] or "",
                    "maximum_marks": float(question["marks"])
                })

        # Evaluate descriptive answers in one AI request
        descriptive_results = {}

        if descriptive_items:
            prompt = f"""
Evaluate the following descriptive examination answers.

Award partial marks fairly based on correctness, relevance,
and the important concepts included in the answer.

Do not award marks merely because an answer is long.
Do not require exact wording when the meaning is correct.
Do not award marks for unrelated content.

Questions and answers:
{json.dumps(descriptive_items, ensure_ascii=False)}

Return valid JSON in this exact structure:

{{
  "results": [
    {{
      "question_id": 1,
      "awarded_marks": 1,
      "feedback": "Brief explanation of the evaluation"
    }}
  ]
}}

The awarded_marks value must be between zero and the
maximum_marks for that question.
Return one result for every supplied question.
"""

            ai_response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a fair academic examiner. "
                            "Evaluate answers carefully and return valid JSON only."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )

            ai_data = json.loads(
                ai_response.choices[0].message.content
            )

            ai_results = ai_data.get("results")

            if not isinstance(ai_results, list):
                raise ValueError("Invalid AI evaluation response.")

            expected_ids = {
                item["question_id"]
                for item in descriptive_items
            }

            for result in ai_results:
                question_id = int(result["question_id"])
                awarded = float(result["awarded_marks"])
                feedback = str(result.get("feedback", "")).strip()

                matching = next(
                    (
                        item for item in descriptive_items
                        if item["question_id"] == question_id
                    ),
                    None
                )

                if not matching or question_id in descriptive_results:
                    raise ValueError("Invalid question in AI evaluation.")

                if not 0 <= awarded <= matching["maximum_marks"]:
                    raise ValueError("AI returned marks outside the allowed range.")

                descriptive_results[question_id] = {
                    "awarded_marks": awarded,
                    "feedback": feedback[:2000]
                }

            if set(descriptive_results) != expected_ids:
                raise ValueError("AI did not evaluate every descriptive answer.")

        # Grade answers and save responses
        total_score = 0.0
        total_marks = 0.0

        for question in questions:
            question_id = question["id"]
            question_type = question["question_type"]
            maximum_marks = float(question["marks"])

            answer = str(
                answers.get(str(question_id), "") or ""
            ).strip()

            awarded_marks = 0.0
            is_correct = None
            feedback = "No answer submitted."

            if question_type == "mcq":
                if answer:
                    is_correct = (
                        answer.strip().casefold()
                        == str(question["correct_answer"]).strip().casefold()
                    )

                    if is_correct:
                        awarded_marks = maximum_marks
                        feedback = "Your selected answer is correct."
                    else:
                        feedback = "Your selected answer is incorrect."

            elif question_type == "descriptive":
                if answer:
                    evaluation = descriptive_results[question_id]
                    awarded_marks = evaluation["awarded_marks"]
                    feedback = evaluation["feedback"] or "Answer evaluated."

            total_score += awarded_marks
            total_marks += maximum_marks

            db.execute(
                text("""
                    INSERT INTO assessment_responses (
                        attempt_id,
                        question_id,
                        answer_text,
                        is_correct,
                        awarded_marks,
                        feedback,
                        submitted_at
                    )
                    VALUES (
                        :attempt_id,
                        :question_id,
                        :answer_text,
                        :is_correct,
                        :awarded_marks,
                        :feedback,
                        NOW()
                    )
                """),
                {
                    "attempt_id": attempt_id,
                    "question_id": question_id,
                    "answer_text": answer or None,
                    "is_correct": is_correct,
                    "awarded_marks": awarded_marks,
                    "feedback": feedback
                }
            )

        percentage = (
            (total_score / total_marks) * 100
            if total_marks > 0
            else 0
        )

        db.execute(
            text("""
                UPDATE assessment_attempts
                SET
                    score = :score,
                    total_marks = :total_marks,
                    percentage = :percentage,
                    status = 'evaluated',
                    submitted_at = NOW()
                WHERE id = :attempt_id
                  AND exam_id = :exam_id
                  AND user_id = :user_id
                  AND status = 'in_progress'
            """),
            {
                "score": total_score,
                "total_marks": total_marks,
                "percentage": percentage,
                "attempt_id": attempt_id,
                "exam_id": exam_id,
                "user_id": user_id
            }
        )

        db.commit()

        return JSONResponse({
            "success": True,
            "message": "Assessment submitted and evaluated successfully.",
            "redirect_url": (
                f"/assessments/theory/results/{attempt_id}"
            )
        })

    except (ValueError, TypeError, json.JSONDecodeError) as error:
        db.rollback()
        print("Assessment submission validation error:", error)

        return JSONResponse(
            {
                "success": False,
                "message": str(error)
            },
            status_code=422
        )

    except Exception as error:
        db.rollback()
        print("Assessment submission error:", error)

        return JSONResponse(
            {
                "success": False,
                "message": (
                    "Unable to evaluate the assessment. "
                    "Your attempt has not been submitted. Please try again."
                )
            },
            status_code=500
        )

    finally:
        db.close()


@assessments_router.get("/assessments/theory/results/{attempt_id}")
def theory_assessment_results(request: Request, attempt_id: int):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        # Fetch assessment attempt and verify ownership
        attempt = db.execute(
            text("""
                SELECT
                    aa.id AS attempt_id,
                    aa.exam_id,
                    aa.score,
                    aa.total_marks,
                    aa.percentage,
                    aa.started_at,
                    aa.submitted_at,
                    aa.status,
                    ae.exam_title,
                    ae.exam_type,
                    s.subject_name
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                JOIN subjects s
                    ON ae.subject_id = s.id
                WHERE aa.id = :attempt_id
                  AND aa.user_id = :user_id
                  AND ae.user_id = :user_id
            """),
            {
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not attempt:
            return JSONResponse(
                {"detail": "Assessment result not found."},
                status_code=404
            )

        if attempt["status"] != "evaluated":
            return RedirectResponse(
                url=f"/assessments/theory/attempt/{attempt['exam_id']}",
                status_code=303
            )

        # Fetch question-wise responses
        responses = db.execute(
            text("""
                SELECT
                    aq.id AS question_id,
                    aq.question_type,
                    aq.question_text,
                    aq.options,
                    aq.correct_answer,
                    aq.expected_answer,
                    aq.explanation,
                    aq.marks AS maximum_marks,
                    ar.answer_text,
                    ar.is_correct,
                    ar.awarded_marks,
                    ar.feedback
                FROM assessment_responses ar
                JOIN assessment_questions aq
                    ON ar.question_id = aq.id
                WHERE ar.attempt_id = :attempt_id
                ORDER BY aq.question_order ASC
            """),
            {"attempt_id": attempt_id}
        ).mappings().all()

        # Convert database rows into dictionaries
        responses = [dict(row) for row in responses]

        # Decode MCQ options
        for response in responses:
            if response["options"] and isinstance(response["options"], str):
                response["options"] = json.loads(response["options"])

        # Prepare assessment details
        attempt_data = dict(attempt)
        percentage = float(attempt_data["percentage"] or 0)

        # Generate performance message
        if percentage >= 90:
            performance_message = (
                "Outstanding performance! "
                "You have demonstrated excellent understanding."
            )

        elif percentage >= 75:
            performance_message = (
                "Great work! "
                "You have a strong understanding of the concepts."
            )

        elif percentage >= 60:
            performance_message = (
                "Good effort! "
                "Revise a few concepts to improve your performance."
            )

        elif percentage >= 40:
            performance_message = (
                "You are making progress. "
                "More practice will help strengthen your understanding."
            )

        else:
            performance_message = (
                "Keep practising. "
                "Review the topics and try another assessment."
            )

        # Display results page
        return templates.TemplateResponse(
            request=request,
            name="theory_results.html",
            context={
                "attempt": attempt_data,
                "responses": responses,
                "performance_message": performance_message
            }
        )

    except Exception as e:
        print("Assessment results error:", str(e))
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load assessment results."},
            status_code=500
        )

    finally:
        db.close()


@assessments_router.get("/assessments/history")
def assessment_history(request: Request):
    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse(url="/login", status_code=303)

    db = SessionLocal()

    try:
        history = db.execute(
            text("""
                SELECT
                    aa.id AS attempt_id,
                    aa.exam_id,
                    aa.score,
                    aa.total_marks,
                    aa.percentage,
                    aa.started_at,
                    aa.submitted_at,
                    aa.status,
                    ae.exam_title,
                    ae.exam_type,
                    s.subject_name
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                JOIN subjects s
                    ON ae.subject_id = s.id
                WHERE aa.user_id = :user_id
                  AND ae.user_id = :user_id
                  AND aa.status = 'evaluated'
                ORDER BY aa.submitted_at DESC, aa.id DESC
            """),
            {"user_id": user_id}
        ).mappings().all()

        history = [dict(row) for row in history]

        # Calculate assessment statistics
        percentages = [
            float(item["percentage"] or 0)
            for item in history
        ]

        average_percentage = (
            sum(percentages) / len(percentages)
            if percentages else 0
        )

        best_percentage = (
            max(percentages)
            if percentages else 0
        )

        return templates.TemplateResponse(
            request=request,
            name="assessment_history.html",
            context={
                "history": history,
                "average_percentage": average_percentage,
                "best_percentage": best_percentage
            }
        )

    except Exception as e:
        print("Assessment history error:", str(e))
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load assessment history."},
            status_code=500
        )

    finally:
        db.close()


@assessments_router.post("/assessments/practical/start/{exam_id}")
def start_practical_assessment(exam_id: int, request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        # 1. Verify that the assessment belongs to the logged-in user
        exam = db.execute(
            text("""
                SELECT
                    id,
                    exam_title,
                    duration_minutes,
                    total_marks
                FROM assessment_exams
                WHERE id = :exam_id
                  AND user_id = :user_id
                  AND exam_type = 'practical'
                  AND status = 'published'
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not exam:
            return JSONResponse(
                {"detail": "Published practical assessment not found."},
                status_code=404
            )

        # 2. Find the latest attempt that is still in progress
        attempt = db.execute(
            text("""
                SELECT
                    id,
                    GREATEST(
                        0,
                        :duration_minutes * 60 -
                        TIMESTAMPDIFF(
                            SECOND,
                            started_at,
                            NOW()
                        )
                    ) AS remaining_seconds
                FROM assessment_attempts
                WHERE exam_id = :exam_id
                  AND user_id = :user_id
                  AND status = 'in_progress'
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
            """),
            {
                "exam_id": exam_id,
                "user_id": user_id,
                "duration_minutes": exam["duration_minutes"]
            }
        ).mappings().first()

        # 3. Resume the existing attempt if time remains
        if attempt and attempt["remaining_seconds"] > 0:

            attempt_id = attempt["id"]

        else:

            # 4. Mark the previous attempt as expired
            if attempt:

                db.execute(
                    text("""
                        UPDATE assessment_attempts
                        SET status = 'expired'
                        WHERE id = :attempt_id
                          AND user_id = :user_id
                          AND status = 'in_progress'
                    """),
                    {
                        "attempt_id": attempt["id"],
                        "user_id": user_id
                    }
                )

            # 5. Create a fresh attempt with a new timer
            result = db.execute(
                text("""
                    INSERT INTO assessment_attempts
                    (
                        exam_id,
                        user_id,
                        started_at,
                        status,
                        total_marks
                    )
                    VALUES
                    (
                        :exam_id,
                        :user_id,
                        CURRENT_TIMESTAMP,
                        'in_progress',
                        :total_marks
                    )
                """),
                {
                    "exam_id": exam_id,
                    "user_id": user_id,
                    "total_marks": exam["total_marks"]
                }
            )

            attempt_id = result.lastrowid

        # 6. Save database changes
        db.commit()

        # 7. Open the attempt page
        return RedirectResponse(
            url=f"/assessments/practical/attempt/{attempt_id}",
            status_code=303
        )

    except Exception:
        db.rollback()
        traceback.print_exc()

        return JSONResponse(
            {
                "detail": "Unable to start the practical assessment."
            },
            status_code=500
        )

    finally:
        db.close()


@assessments_router.get("/assessments/practical/attempt/{attempt_id}")
def practical_attempt_page(attempt_id: int, request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        # 1. Fetch attempt details and calculate remaining time
        attempt = db.execute(
            text("""
                SELECT
                    aa.id AS attempt_id,
                    aa.exam_id,
                    aa.started_at,
                    aa.status,
                    ae.exam_title,
                    ae.duration_minutes,
                    ae.total_marks,
                    s.subject_name,
                    t.topic_name,
                    GREATEST(
                        0,
                        ae.duration_minutes * 60 -
                        TIMESTAMPDIFF(
                            SECOND,
                            aa.started_at,
                            NOW()
                        )
                    ) AS remaining_seconds
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                JOIN subjects s
                    ON ae.subject_id = s.id
                LEFT JOIN topics t
                    ON ae.topic_id = t.id
                WHERE aa.id = :attempt_id
                  AND aa.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'published'
            """),
            {
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        ).mappings().first()

        # 2. Check whether the attempt exists
        if not attempt:
            return JSONResponse(
                {
                    "detail": "Practical assessment attempt not found."
                },
                status_code=404
            )

        # 3. Display expiry page for an already-expired attempt
        if attempt["status"] == "expired":
            return templates.TemplateResponse(
                request=request,
                name="practical_expired.html",
                context={
                    "attempt": attempt,
                    "user_name": request.session.get("user_name")
                },
                status_code=410
            )

        # 4. Reject submitted or evaluated attempts
        if attempt["status"] != "in_progress":
            return JSONResponse(
                {
                    "detail": "This assessment attempt is no longer active."
                },
                status_code=400
            )

        # 5. Check whether the active attempt has reached its deadline
        if attempt["remaining_seconds"] <= 0:

            db.execute(
                text("""
                    UPDATE assessment_attempts
                    SET status = 'expired'
                    WHERE id = :attempt_id
                      AND user_id = :user_id
                      AND status = 'in_progress'
                """),
                {
                    "attempt_id": attempt_id,
                    "user_id": user_id
                }
            )

            db.commit()

            return templates.TemplateResponse(
                request=request,
                name="practical_expired.html",
                context={
                    "attempt": attempt,
                    "user_name": request.session.get("user_name")
                },
                status_code=410
            )

        # 6. Fetch programming questions
        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_text,
                    programming_language,
                    starter_code,
                    marks,
                    question_order
                FROM assessment_questions
                WHERE exam_id = :exam_id
                  AND question_type = 'programming'
                ORDER BY question_order
            """),
            {
                "exam_id": attempt["exam_id"]
            }
        ).mappings().all()

        # 7. Fetch previously saved answers
        responses = db.execute(
            text("""
                SELECT
                    question_id,
                    answer_text
                FROM assessment_responses
                WHERE attempt_id = :attempt_id
            """),
            {
                "attempt_id": attempt_id
            }
        ).mappings().all()

        saved_answers = {
            row["question_id"]: row["answer_text"]
            for row in responses
        }

        # 8. Display the practical assessment page
        return templates.TemplateResponse(
            request=request,
            name="practical_attempt.html",
            context={
                "attempt": attempt,
                "questions": questions,
                "saved_answers": saved_answers,
                "user_name": request.session.get("user_name")
            }
        )

    except Exception:
        db.rollback()
        traceback.print_exc()

        return JSONResponse(
            {
                "detail": "Unable to load the practical assessment."
            },
            status_code=500
        )

    finally:
        db.close()


@assessments_router.post("/assessments/practical/save-answer/{attempt_id}")
async def save_practical_answer(attempt_id: int, request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

    db = SessionLocal()

    try:
        form = await request.form()

        question_id = int(form.get("question_id", 0))
        answer_text = str(form.get("answer_text", ""))

        if len(answer_text) > 20000:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Code exceeds the 20,000-character limit."
                },
                status_code=400
            )

        # Verify the active attempt and its deadline
        attempt = db.execute(
            text("""
                SELECT
                    aa.id,
                    aa.exam_id,
                    ae.duration_minutes,
                    TIMESTAMPDIFF(
                        SECOND,
                        aa.started_at,
                        NOW()
                    ) AS elapsed_seconds
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                WHERE aa.id = :attempt_id
                  AND aa.user_id = :user_id
                  AND aa.status = 'in_progress'
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'published'
            """),
            {
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not attempt:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Active attempt not found."
                },
                status_code=404
            )

        # Check the timer independently
        if attempt["elapsed_seconds"] >= attempt["duration_minutes"] * 60:

            db.execute(
                text("""
                    UPDATE assessment_attempts
                    SET status = 'expired'
                    WHERE id = :attempt_id
                      AND user_id = :user_id
                      AND status = 'in_progress'
                """),
                {
                    "attempt_id": attempt_id,
                    "user_id": user_id
                }
            )

            db.commit()

            return JSONResponse(
                {
                    "success": False,
                    "message": "Assessment time has expired. Code can no longer be saved."
                },
                status_code=410
            )

        # Verify that the question belongs to this assessment
        question = db.execute(
            text("""
                SELECT id
                FROM assessment_questions
                WHERE id = :question_id
                  AND exam_id = :exam_id
                  AND question_type = 'programming'
            """),
            {
                "question_id": question_id,
                "exam_id": attempt["exam_id"]
            }
        ).mappings().first()

        if not question:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Invalid question."
                },
                status_code=400
            )

        # Update an existing answer or insert a new one
        existing = db.execute(
            text("""
                SELECT id
                FROM assessment_responses
                WHERE attempt_id = :attempt_id
                  AND question_id = :question_id
            """),
            {
                "attempt_id": attempt_id,
                "question_id": question_id
            }
        ).mappings().first()

        if existing:
            db.execute(
                text("""
                    UPDATE assessment_responses
                    SET answer_text = :answer_text
                    WHERE id = :response_id
                """),
                {
                    "answer_text": answer_text,
                    "response_id": existing["id"]
                }
            )
        else:
            db.execute(
                text("""
                    INSERT INTO assessment_responses (
                        attempt_id,
                        question_id,
                        answer_text
                    )
                    VALUES (
                        :attempt_id,
                        :question_id,
                        :answer_text
                    )
                """),
                {
                    "attempt_id": attempt_id,
                    "question_id": question_id,
                    "answer_text": answer_text
                }
            )

        db.commit()

        return JSONResponse({
            "success": True,
            "message": "Code saved successfully."
        })

    except (ValueError, TypeError):
        db.rollback()
        return JSONResponse(
            {
                "success": False,
                "message": "Invalid question or answer data."
            },
            status_code=400
        )

    except Exception:
        db.rollback()
        traceback.print_exc()

        return JSONResponse(
            {
                "success": False,
                "message": "Unable to save code."
            },
            status_code=500
        )

    finally:
        db.close()

@assessments_router.post("/assessments/practical/run/{attempt_id}")
async def run_practical_code(attempt_id: int, request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return JSONResponse(
            {"success": False, "message": "Please log in again."},
            status_code=401
        )

    db = SessionLocal()

    try:
        form = await request.form()

        question_id = int(form.get("question_id", 0))
        source_code = str(form.get("answer_text", ""))

        if not source_code.strip():
            return JSONResponse({
                "success": False,
                "message": "Please write your Python code before running it."
            }, status_code=400)

        if len(source_code) > 20000:
            return JSONResponse({
                "success": False,
                "message": "Code exceeds the 20,000-character limit."
            }, status_code=400)

        # Verify attempt ownership and deadline
        attempt = db.execute(
            text("""
                SELECT
                    aa.id,
                    aa.exam_id,
                    ae.duration_minutes,
                    TIMESTAMPDIFF(
                        SECOND,
                        aa.started_at,
                        NOW()
                    ) AS elapsed_seconds
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                WHERE aa.id = :attempt_id
                  AND aa.user_id = :user_id
                  AND aa.status = 'in_progress'
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'published'
            """),
            {
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not attempt:
            return JSONResponse({
                "success": False,
                "message": "Active assessment attempt not found."
            }, status_code=404)

        # Enforce the server-side deadline
        if attempt["elapsed_seconds"] >= attempt["duration_minutes"] * 60:

            db.execute(
                text("""
                    UPDATE assessment_attempts
                    SET status = 'expired'
                    WHERE id = :attempt_id
                      AND status = 'in_progress'
                """),
                {"attempt_id": attempt_id}
            )

            db.commit()

            return JSONResponse({
                "success": False,
                "message": "Assessment time has expired."
            }, status_code=410)

        # Retrieve the question and its test cases
        question = db.execute(
            text("""
                SELECT id, test_cases
                FROM assessment_questions
                WHERE id = :question_id
                  AND exam_id = :exam_id
                  AND question_type = 'programming'
            """),
            {
                "question_id": question_id,
                "exam_id": attempt["exam_id"]
            }
        ).mappings().first()

        if not question:
            return JSONResponse({
                "success": False,
                "message": "Invalid programming question."
            }, status_code=400)

        # Decode test cases
        test_cases = question["test_cases"]

        if isinstance(test_cases, str):
            test_cases = json.loads(test_cases)

        if not isinstance(test_cases, list) or not test_cases:
            return JSONResponse({
                "success": False,
                "message": "No valid test cases are available."
            }, status_code=400)

        # Limit execution requests per question
        if len(test_cases) > 10:
            return JSONResponse({
                "success": False,
                "message": "This question has too many test cases."
            }, status_code=400)

        results = []
        passed_count = 0

        # Execute each test case separately
        for index, test_case in enumerate(test_cases, start=1):

            if not isinstance(test_case, dict):
                return JSONResponse({
                    "success": False,
                    "message": "Invalid test-case format."
                }, status_code=400)

            test_input = test_case.get("input", "")
            expected_output = test_case.get("expected_output")

            if not isinstance(test_input, str) or not isinstance(expected_output, str):
                return JSONResponse({
                    "success": False,
                    "message": "Invalid test-case input or expected output."
                }, status_code=400)

            if len(test_input) > 10000 or len(expected_output) > 10000:
                return JSONResponse({
                    "success": False,
                    "message": "Test-case data exceeds the allowed size."
                }, status_code=400)

            execution = execute_python(
                source_code,
                test_input
            )

            # A service failure should not be treated as a wrong answer
            if execution["status"] in (
                "Service Error",
                "Processing Timeout"
            ):
                return JSONResponse({
                    "success": False,
                    "message": "The code execution service is temporarily unavailable. Please try again."
                }, status_code=503)

            actual_output = execution.get("stdout") or ""

            passed = (
                execution["success"]
                and actual_output.strip() == expected_output.strip()
            )

            if passed:
                passed_count += 1

            results.append({
                "test_case": index,
                "passed": passed,
                "status": execution["status"],
                "expected_output": expected_output,
                "actual_output": actual_output,
                "error": (
                    execution.get("stderr")
                    or execution.get("compile_output")
                )
            })

        return JSONResponse({
            "success": True,
            "passed": passed_count,
            "total": len(test_cases),
            "all_passed": passed_count == len(test_cases),
            "results": results,
            "message": f"{passed_count} of {len(test_cases)} test cases passed."
        })

    except (ValueError, TypeError, json.JSONDecodeError):
        return JSONResponse({
            "success": False,
            "message": "Invalid question or test-case data."
        }, status_code=400)

    except Exception:
        db.rollback()
        traceback.print_exc()

        return JSONResponse({
            "success": False,
            "message": "Unable to execute the submitted code."
        }, status_code=500)

    finally:
        db.close()

@assessments_router.post("/assessments/practical/submit/{attempt_id}")
def submit_practical_assessment(attempt_id: int, request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        # 1. Verify ownership, assessment type, and attempt status
        attempt = db.execute(
            text("""
                SELECT
                    aa.id,
                    aa.exam_id,
                    aa.total_marks,
                    ae.duration_minutes,
                    TIMESTAMPDIFF(
                        SECOND,
                        aa.started_at,
                        NOW()
                    ) AS elapsed_seconds
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                WHERE aa.id = :attempt_id
                  AND aa.user_id = :user_id
                  AND aa.status = 'in_progress'
                  AND ae.exam_type = 'practical'
                  AND ae.status = 'published'
            """),
            {
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not attempt:
            return JSONResponse(
                {
                    "success": False,
                    "message": "Active practical assessment not found."
                },
                status_code=404
            )

        # 2. Enforce the assessment deadline
        if attempt["elapsed_seconds"] >= attempt["duration_minutes"] * 60:

            db.execute(
                text("""
                    UPDATE assessment_attempts
                    SET status = 'expired'
                    WHERE id = :attempt_id
                      AND user_id = :user_id
                      AND status = 'in_progress'
                """),
                {
                    "attempt_id": attempt_id,
                    "user_id": user_id
                }
            )

            db.commit()

            return JSONResponse(
                {
                    "success": False,
                    "message": "Assessment time has expired."
                },
                status_code=410
            )

        # 3. Retrieve all programming questions
        questions = db.execute(
            text("""
                SELECT
                    id,
                    question_text,
                    test_cases,
                    marks
                FROM assessment_questions
                WHERE exam_id = :exam_id
                  AND question_type = 'programming'
                ORDER BY question_order
            """),
            {
                "exam_id": attempt["exam_id"]
            }
        ).mappings().all()

        if not questions:
            return JSONResponse(
                {
                    "success": False,
                    "message": "No programming questions are available."
                },
                status_code=400
            )

        # 4. Retrieve the student's saved code
        responses = db.execute(
            text("""
                SELECT question_id, answer_text
                FROM assessment_responses
                WHERE attempt_id = :attempt_id
            """),
            {
                "attempt_id": attempt_id
            }
        ).mappings().all()

        saved_answers = {
            row["question_id"]: row["answer_text"] or ""
            for row in responses
        }

        total_score = 0.0
        evaluated_questions = []

        # 5. Evaluate every question against its test cases
        for question in questions:

            source_code = saved_answers.get(question["id"], "")

            test_cases = question["test_cases"]

            if isinstance(test_cases, str):
                test_cases = json.loads(test_cases)

            if not isinstance(test_cases, list) or not test_cases:
                return JSONResponse(
                    {
                        "success": False,
                        "message": (
                            f"Question {question['id']} does not have "
                            "valid test cases. Please contact the administrator."
                        )
                    },
                    status_code=400
                )

            if len(test_cases) > 10:
                return JSONResponse(
                    {
                        "success": False,
                        "message": "A question exceeds the maximum test-case limit."
                    },
                    status_code=400
                )

            passed_count = 0
            total_cases = len(test_cases)

            if source_code.strip():

                for test_case in test_cases:

                    if not isinstance(test_case, dict):
                        return JSONResponse(
                            {
                                "success": False,
                                "message": "Invalid test-case format."
                            },
                            status_code=400
                        )

                    test_input = test_case.get("input", "")
                    expected_output = test_case.get("expected_output")

                    if (
                        not isinstance(test_input, str)
                        or not isinstance(expected_output, str)
                        or len(test_input) > 10000
                        or len(expected_output) > 10000
                    ):
                        return JSONResponse(
                            {
                                "success": False,
                                "message": "Invalid or oversized test-case data."
                            },
                            status_code=400
                        )

                    execution = execute_python(
                        source_code,
                        test_input
                    )

                    # Do not finalize an assessment if Judge0 is unavailable
                    if execution.get("status") in (
                        "Service Error",
                        "Processing Timeout"
                    ):
                        return JSONResponse(
                            {
                                "success": False,
                                "message": (
                                    "The code execution service is temporarily "
                                    "unavailable. Your assessment has not been "
                                    "submitted. Please try again."
                                )
                            },
                            status_code=503
                        )

                    actual_output = execution.get("stdout") or ""

                    if (
                        execution.get("success")
                        and actual_output.strip() == expected_output.strip()
                    ):
                        passed_count += 1

            # 6. Calculate proportional marks
            question_marks = float(question["marks"] or 0)

            awarded_marks = round(
                question_marks * passed_count / total_cases,
                2
            )

            total_score += awarded_marks

            feedback = (
                f"{passed_count} out of {total_cases} test cases passed."
            )

            if not source_code.strip():
                feedback = "No code was submitted."

            evaluated_questions.append({
                "question_id": question["id"],
                "answer_text": source_code,
                "is_correct": passed_count == total_cases,
                "awarded_marks": awarded_marks,
                "feedback": feedback
            })

        # 7. Calculate final percentage
        maximum_marks = float(attempt["total_marks"] or 0)

        percentage = (
            round((total_score / maximum_marks) * 100, 2)
            if maximum_marks > 0 else 0
        )

        # 8. Save question-wise evaluation
        for item in evaluated_questions:

            existing = db.execute(
                text("""
                    SELECT id
                    FROM assessment_responses
                    WHERE attempt_id = :attempt_id
                      AND question_id = :question_id
                """),
                {
                    "attempt_id": attempt_id,
                    "question_id": item["question_id"]
                }
            ).mappings().first()

            if existing:
                db.execute(
                    text("""
                        UPDATE assessment_responses
                        SET
                            answer_text = :answer_text,
                            is_correct = :is_correct,
                            awarded_marks = :awarded_marks,
                            feedback = :feedback,
                            submitted_at = CURRENT_TIMESTAMP
                        WHERE id = :response_id
                    """),
                    {
                        **item,
                        "response_id": existing["id"]
                    }
                )
            else:
                db.execute(
                    text("""
                        INSERT INTO assessment_responses (
                            attempt_id,
                            question_id,
                            answer_text,
                            is_correct,
                            awarded_marks,
                            feedback,
                            submitted_at
                        )
                        VALUES (
                            :attempt_id,
                            :question_id,
                            :answer_text,
                            :is_correct,
                            :awarded_marks,
                            :feedback,
                            CURRENT_TIMESTAMP
                        )
                    """),
                    {
                        "attempt_id": attempt_id,
                        **item
                    }
                )

        # 9. Mark the attempt as evaluated
        db.execute(
            text("""
                UPDATE assessment_attempts
                SET
                    score = :score,
                    total_marks = :total_marks,
                    percentage = :percentage,
                    status = 'evaluated',
                    submitted_at = CURRENT_TIMESTAMP
                WHERE id = :attempt_id
                  AND user_id = :user_id
                  AND status = 'in_progress'
            """),
            {
                "score": round(total_score, 2),
                "total_marks": maximum_marks,
                "percentage": percentage,
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        )

        db.commit()

        # 10. Redirect to the practical results page
        return RedirectResponse(
            url=f"/assessments/practical/results/{attempt_id}",
            status_code=303
        )

    except (ValueError, TypeError, json.JSONDecodeError):
        db.rollback()
        return JSONResponse(
            {
                "success": False,
                "message": "Invalid assessment or test-case data."
            },
            status_code=400
        )

    except Exception:
        db.rollback()
        traceback.print_exc()

        return JSONResponse(
            {
                "success": False,
                "message": "Unable to submit the practical assessment."
            },
            status_code=500
        )

    finally:
        db.close()

@assessments_router.get("/assessments/practical/results/{attempt_id}")
def practical_assessment_results(attempt_id: int, request: Request):

    user_id = request.session.get("user_id")

    if not user_id:
        return RedirectResponse("/login", status_code=303)

    db = SessionLocal()

    try:
        # 1. Retrieve the evaluated attempt
        attempt = db.execute(
            text("""
                SELECT
                    aa.id AS attempt_id,
                    aa.exam_id,
                    aa.score,
                    aa.total_marks,
                    aa.percentage,
                    aa.started_at,
                    aa.submitted_at,
                    ae.exam_title,
                    s.subject_name,
                    t.topic_name
                FROM assessment_attempts aa
                JOIN assessment_exams ae
                    ON aa.exam_id = ae.id
                JOIN subjects s
                    ON ae.subject_id = s.id
                LEFT JOIN topics t
                    ON ae.topic_id = t.id
                WHERE aa.id = :attempt_id
                  AND aa.user_id = :user_id
                  AND ae.exam_type = 'practical'
                  AND aa.status = 'evaluated'
            """),
            {
                "attempt_id": attempt_id,
                "user_id": user_id
            }
        ).mappings().first()

        if not attempt:
            return JSONResponse(
                {"detail": "Evaluated practical assessment not found."},
                status_code=404
            )

        # 2. Retrieve question-wise evaluation
        responses = db.execute(
            text("""
                SELECT
                    q.question_text,
                    q.marks,
                    r.answer_text,
                    r.is_correct,
                    r.awarded_marks,
                    r.feedback
                FROM assessment_responses r
                JOIN assessment_questions q
                    ON r.question_id = q.id
                WHERE r.attempt_id = :attempt_id
                  AND q.exam_id = :exam_id
                  AND q.question_type = 'programming'
                ORDER BY q.question_order
            """),
            {
                "attempt_id": attempt_id,
                "exam_id": attempt["exam_id"]
            }
        ).mappings().all()

        # 3. Display results
        return templates.TemplateResponse(
            request=request,
            name="practical_results.html",
            context={
                "attempt": attempt,
                "responses": responses,
                "user_name": request.session.get("user_name")
            }
        )

    except Exception:
        db.rollback()
        traceback.print_exc()

        return JSONResponse(
            {"detail": "Unable to load practical assessment results."},
            status_code=500
        )

    finally:
        db.close()