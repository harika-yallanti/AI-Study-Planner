
import os
import smtplib

from email.message import EmailMessage
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text
from dotenv import load_dotenv

from app.database import SessionLocal

load_dotenv()


def send_email(recipient, subject, body):
    sender = os.getenv("SMTP_EMAIL")
    password = os.getenv("SMTP_PASSWORD")

    if not sender or not password:
        raise ValueError("SMTP email settings are missing.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient
    message.set_content(body)

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(message)


def send_missed_study_email(
    recipient,
    topic_name,
    planned_date,
    planned_time
):
    send_email(
        recipient,
        "Missed Study Session - AI Study Planner",
        f"""Hello,

You missed your planned study session.

Topic: {topic_name}
Planned date: {planned_date}
Planned time: {planned_time}

Please visit your AI Study Planner and schedule
this topic for another time.

Keep learning and try again!

AI Study Planner
"""
    )


def send_upcoming_study_email(
    recipient,
    topic_name,
    planned_date,
    planned_time,
    planned_minutes
):
    send_email(
        recipient,
        "Reminder: Your study session starts in 1 hour!",
        f"""Hello,

This is a friendly reminder that your study session
is scheduled to start in approximately one hour.

Topic: {topic_name}
Date: {planned_date}
Time: {planned_time}
Duration: {planned_minutes} minutes

Please be ready to start your session on time.
If you do not start your session, it may be marked
as missed and you may receive a missed-session email.

Open your AI Study Planner and get ready to study!

Happy learning,
AI Study Planner
"""
    )


def check_upcoming_study_sessions():
    db = SessionLocal()

    try:
        # Find sessions starting approximately one hour from now.
        upcoming_sessions = db.execute(
            text("""
                SELECT
                    p.id,
                    u.email,
                    t.topic_name,
                    p.planned_date,
                    p.planned_time,
                    p.planned_minutes
                FROM planned_study_sessions p
                JOIN users u
                    ON p.user_id = u.id
                JOIN topics t
                    ON p.topic_id = t.id
                JOIN subjects s
                    ON t.subject_id = s.id
                   AND s.user_id = p.user_id
                WHERE p.status = 'planned'
                  AND p.one_hour_reminder_sent = 0
                  AND TIMESTAMP(p.planned_date, p.planned_time)
                      > NOW() + INTERVAL 59 MINUTE
                  AND TIMESTAMP(p.planned_date, p.planned_time)
                      <= NOW() + INTERVAL 60 MINUTE
            """)
        ).fetchall()

        for session in upcoming_sessions:
            try:
                send_upcoming_study_email(
                    recipient=session.email,
                    topic_name=session.topic_name,
                    planned_date=session.planned_date,
                    planned_time=session.planned_time,
                    planned_minutes=session.planned_minutes
                )

                db.execute(
                    text("""
                        UPDATE planned_study_sessions
                        SET one_hour_reminder_sent = 1
                        WHERE id = :session_id
                          AND status = 'planned'
                          AND one_hour_reminder_sent = 0
                    """),
                    {"session_id": session.id}
                )
                db.commit()

                print(
                    f"One-hour reminder sent for session {session.id}"
                )

            except Exception as error:
                db.rollback()
                print(
                    f"Could not send upcoming reminder for "
                    f"session {session.id}: {error}"
                )

    finally:
        db.close()


def check_missed_study_sessions():
    db = SessionLocal()

    try:
        missed_sessions = db.execute(
            text("""
                SELECT
                    p.id,
                    u.email,
                    t.topic_name,
                    p.planned_date,
                    p.planned_time
                FROM planned_study_sessions p
                JOIN users u
                    ON p.user_id = u.id
                JOIN topics t
                    ON p.topic_id = t.id
                JOIN subjects s
                    ON t.subject_id = s.id
                   AND s.user_id = p.user_id
                WHERE p.status = 'planned'
                  AND p.reminder_sent = 0
                  AND TIMESTAMP(p.planned_date, p.planned_time)
                  + INTERVAL p.planned_minutes MINUTE <= NOW()
            """)
        ).fetchall()

        for session in missed_sessions:
            try:
                send_missed_study_email(
                    recipient=session.email,
                    topic_name=session.topic_name,
                    planned_date=session.planned_date,
                    planned_time=session.planned_time
                )

                db.execute(
                    text("""
                        UPDATE planned_study_sessions
                        SET status = 'missed',
                            reminder_sent = 1
                        WHERE id = :session_id
                          AND status = 'planned'
                          AND reminder_sent = 0
                    """),
                    {"session_id": session.id}
                )
                db.commit()

                print(
                    f"Missed-study email sent for session {session.id}"
                )

            except Exception as error:
                db.rollback()
                print(
                    f"Could not send missed-study email for "
                    f"session {session.id}: {error}"
                )

    finally:
        db.close()


scheduler = BackgroundScheduler(timezone="Asia/Kolkata")


def start_reminder_scheduler():
    if scheduler.running:
        return

    scheduler.add_job(
        check_upcoming_study_sessions,
        trigger="interval",
        minutes=1,
        id="upcoming_study_reminders",
        replace_existing=True,
        max_instances=1
    )

    scheduler.add_job(
        check_missed_study_sessions,
        trigger="interval",
        minutes=1,
        id="missed_study_reminders",
        replace_existing=True,
        max_instances=1
    )

    scheduler.start()


def stop_reminder_scheduler():
    if scheduler.running:
        scheduler.shutdown()
