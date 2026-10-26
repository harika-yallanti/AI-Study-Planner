
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from the project root .env file
load_dotenv()

# Read MySQL connection details
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "3306")
DB_NAME = os.getenv("DB_NAME")

# Check that required settings are available
if not DB_USER or not DB_PASSWORD or not DB_NAME:
    raise ValueError("Missing database settings. Check your .env file.")

# Encode special characters in the password
encoded_password = quote_plus(DB_PASSWORD)

# Create the database connection URL
DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{encoded_password}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Create the database engine
engine = create_engine(
    DATABASE_URL,
    echo=True
)

# Create a database session factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for database models
Base = declarative_base()


# Provide a database session to FastAPI routes
def get_db():
    db = SessionLocal()

    try:
        yield db
        db.commit()

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
