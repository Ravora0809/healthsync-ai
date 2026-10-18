import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, JSON, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.session import Base
class User(Base):
    __tablename__="users"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    full_name: Mapped[str]=mapped_column(String(120),nullable=False)
    email: Mapped[str]=mapped_column(String(255),unique=True,index=True,nullable=False)
    password_hash: Mapped[str]=mapped_column(String(255),nullable=False)
    is_active: Mapped[bool]=mapped_column(Boolean,default=True,nullable=False)
    email_verified: Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
class PendingSignup(Base):
    __tablename__="pending_signups"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    full_name: Mapped[str]=mapped_column(String(120),nullable=False)
    email: Mapped[str]=mapped_column(String(255),unique=True,index=True,nullable=False)
    password_hash: Mapped[str]=mapped_column(String(255),nullable=False)
    otp_hash: Mapped[str]=mapped_column(String(64),nullable=False)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    attempts: Mapped[int]=mapped_column(Integer,default=0,nullable=False)
    last_sent_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
class MedicalRecord(Base):
    __tablename__="medical_records"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True,nullable=False)
    title: Mapped[str]=mapped_column(String(200),nullable=False)
    record_type: Mapped[str]=mapped_column(String(40),default="other",nullable=False)
    provider_name: Mapped[str|None]=mapped_column(String(200))
    doctor_name: Mapped[str|None]=mapped_column(String(200))
    record_date: Mapped[date|None]=mapped_column(Date)
    storage_key: Mapped[str]=mapped_column(String(600),nullable=False)
    original_filename: Mapped[str]=mapped_column(String(255),nullable=False)
    file_sha256: Mapped[str]=mapped_column(String(64),nullable=False)
    extracted_text: Mapped[str|None]=mapped_column(Text)
    extracted_data: Mapped[dict]=mapped_column(JSON,default=dict,nullable=False)
    verification_status: Mapped[str]=mapped_column(String(30),default="pending_review",nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
class Vaccination(Base):
    __tablename__="vaccinations"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True,nullable=False)
    name: Mapped[str]=mapped_column(String(160),nullable=False)
    dose: Mapped[str|None]=mapped_column(String(80))
    date_received: Mapped[date|None]=mapped_column(Date)
    next_due: Mapped[date|None]=mapped_column(Date)
    provider: Mapped[str|None]=mapped_column(String(200))
    notes: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
class Reminder(Base):
    __tablename__="reminders"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True,nullable=False)
    title: Mapped[str]=mapped_column(String(200),nullable=False)
    description: Mapped[str|None]=mapped_column(Text)
    due_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    is_completed: Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)
class AuditEvent(Base):
    __tablename__="audit_events"
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),ForeignKey("users.id",ondelete="CASCADE"),index=True,nullable=False)
    record_id: Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True),ForeignKey("medical_records.id",ondelete="SET NULL"))
    action: Mapped[str]=mapped_column(String(80),nullable=False)
    details: Mapped[dict]=mapped_column(JSON,default=dict,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),nullable=False)

class HealthProfile(Base):
    __tablename__ = "health_profiles"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

class SecureShare(Base):
    __tablename__ = "secure_shares"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    recipient_name: Mapped[str] = mapped_column(String(200), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    record_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    purpose: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
