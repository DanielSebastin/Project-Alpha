import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    profile = relationship(
        "Profile",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    resumes = relationship(
        "Resume",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    owned_blueprints = relationship(
        "Blueprint", back_populates="owner", cascade="all, delete-orphan"
    )
    blueprint_memberships = relationship(
        "BlueprintMember", back_populates="user", cascade="all, delete-orphan"
    )
    sent_blueprint_invitations = relationship(
        "BlueprintInvitation", back_populates="sender", foreign_keys="BlueprintInvitation.sender_id", cascade="all, delete-orphan"
    )
    received_blueprint_invitations = relationship(
        "BlueprintInvitation", back_populates="receiver", foreign_keys="BlueprintInvitation.receiver_id", cascade="all, delete-orphan"
    )
    blueprint_join_requests = relationship(
        "BlueprintJoinRequest", back_populates="user", cascade="all, delete-orphan"
    )
