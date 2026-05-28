from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    telegram_handle: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # "teacher" | "student"
    invite_code: Mapped[Optional[str]] = mapped_column(String(16), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    taught_links: Mapped[List["TeacherStudentLink"]] = relationship(
        "TeacherStudentLink", foreign_keys="TeacherStudentLink.teacher_id", back_populates="teacher"
    )
    student_links: Mapped[List["TeacherStudentLink"]] = relationship(
        "TeacherStudentLink", foreign_keys="TeacherStudentLink.student_id", back_populates="student"
    )
    assignments_given: Mapped[List["Assignment"]] = relationship(
        "Assignment", foreign_keys="Assignment.teacher_id", back_populates="teacher"
    )
    assignments_received: Mapped[List["Assignment"]] = relationship(
        "Assignment", foreign_keys="Assignment.student_id", back_populates="student"
    )
    # ConversationState is queried directly by telegram_id — no ORM relationship needed


class TeacherStudentLink(Base):
    __tablename__ = "teacher_student_links"
    __table_args__ = (UniqueConstraint("teacher_id", "student_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    teacher: Mapped["User"] = relationship(
        "User", foreign_keys=[teacher_id], back_populates="taught_links"
    )
    student: Mapped["User"] = relationship(
        "User", foreign_keys=[student_id], back_populates="student_links"
    )


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    raw_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    teacher: Mapped["User"] = relationship(
        "User", foreign_keys=[teacher_id], back_populates="assignments_given"
    )
    student: Mapped["User"] = relationship(
        "User", foreign_keys=[student_id], back_populates="assignments_received"
    )
    reminders: Mapped[List["Reminder"]] = relationship(
        "Reminder", back_populates="assignment", cascade="all, delete-orphan"
    )
    progress_updates: Mapped[List["ProgressUpdate"]] = relationship(
        "ProgressUpdate", back_populates="assignment", cascade="all, delete-orphan"
    )
    submission: Mapped[Optional["Submission"]] = relationship(
        "Submission", back_populates="assignment", uselist=False, cascade="all, delete-orphan"
    )
    feedback: Mapped[Optional["Feedback"]] = relationship(
        "Feedback", back_populates="assignment", uselist=False, cascade="all, delete-orphan"
    )


class ProgressUpdate(Base):
    __tablename__ = "progress_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    interpreted_status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="progress_updates")
    student: Mapped["User"] = relationship("User")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assignments.id"), unique=True, nullable=False
    )
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    text_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    file_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    file_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="submission")
    student: Mapped["User"] = relationship("User")


class Feedback(Base):
    __tablename__ = "feedbacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("assignments.id"), unique=True, nullable=False
    )
    teacher_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    raw_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    formatted_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="feedback")
    teacher: Mapped["User"] = relationship("User")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assignment_id: Mapped[int] = mapped_column(Integer, ForeignKey("assignments.id"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reminder_type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    assignment: Mapped["Assignment"] = relationship("Assignment", back_populates="reminders")
    student: Mapped["User"] = relationship("User")


class ConversationState(Base):
    __tablename__ = "conversation_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    state: Mapped[str] = mapped_column(String(64), nullable=False, default="idle")
    context_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # No ORM relationship — looked up directly via telegram_id in application code
