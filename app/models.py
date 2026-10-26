from sqlalchemy import Column, Integer, String, TIMESTAMP, Boolean, text
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String(100),
        nullable=False
    )

    email = Column(
        String(150),
        unique=True,
        nullable=False
    )

    password_hash = Column(
        String(255),
        nullable=False
    )

    role = Column(
        String(20),
        nullable=False,
        default="student",
        server_default=text("'student'")
    )

    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1")
    )

    created_at = Column(
        TIMESTAMP,
        server_default=text("CURRENT_TIMESTAMP")
    )
