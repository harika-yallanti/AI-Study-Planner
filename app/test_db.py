from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

try:
    result = db.execute(
        text("SELECT COUNT(*) FROM users")
    )

    user_count = result.scalar()

    print("Database query successful!")
    print("Number of registered users:", user_count)

except Exception as error:
    print("Database query failed:", error)
    db.rollback()

finally:
    db.close()