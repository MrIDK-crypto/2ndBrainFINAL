"""
SQLAlchemy ORM Models for 2nd Brain
Enterprise-grade multi-tenant data models with full audit trail
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum as PyEnum

from sqlalchemy import (
    create_engine, Column, String, Text, DateTime, Boolean, Integer,
    Float, ForeignKey, Enum, JSON, LargeBinary, Index, UniqueConstraint,
    Table, event
)
from sqlalchemy.orm import (
    declarative_base, relationship, sessionmaker, Session, validates
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func

from .config import get_database_url


# Create base class
Base = declarative_base()


# ============================================================================
# ENUMS
# ============================================================================

class UserRole(PyEnum):
    """User roles for access control"""
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class TenantPlan(PyEnum):
    """Subscription plans"""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class DocumentStatus(PyEnum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    CLASSIFIED = "classified"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class DocumentClassification(PyEnum):
    """Work/Personal classification"""
    WORK = "work"
    PERSONAL = "personal"
    SPAM = "spam"
    UNKNOWN = "unknown"


class ConnectorType(PyEnum):
    """Supported integration types"""
    GMAIL = "gmail"
    SLACK = "slack"
    BOX = "box"
    GITHUB = "github"
    ONEDRIVE = "onedrive"
    GOOGLE_DRIVE = "google_drive"
    NOTION = "notion"
    PUBMED = "pubmed"
    RESEARCHGATE = "researchgate"
    GOOGLESCHOLAR = "googlescholar"
    WEBSCRAPER = "webscraper"


class ConnectorStatus(PyEnum):
    """Connector connection status"""
    NOT_CONFIGURED = "not_configured"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class GapCategory(PyEnum):
    """Knowledge gap categories"""
    DECISION = "decision"
    TECHNICAL = "technical"
    PROCESS = "process"
    CONTEXT = "context"
    RELATIONSHIP = "relationship"
    TIMELINE = "timeline"
    OUTCOME = "outcome"
    RATIONALE = "rationale"


class GapStatus(PyEnum):
    """Knowledge gap status"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    ANSWERED = "answered"
    VERIFIED = "verified"
    CLOSED = "closed"


class VideoStatus(PyEnum):
    """Video generation status"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def generate_uuid() -> str:
    """Generate a new UUID string"""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Get current UTC timestamp"""
    return datetime.now(timezone.utc)


# ============================================================================
# TENANT MODEL (Multi-tenancy)
# ============================================================================

class Tenant(Base):
    """
    Tenant model for multi-tenancy.
    Each tenant (organization) has isolated data.
    """
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)

    # Subscription
    plan = Column(Enum(TenantPlan), default=TenantPlan.FREE, nullable=False)
    plan_started_at = Column(DateTime(timezone=True))
    plan_expires_at = Column(DateTime(timezone=True))

    # Storage
    data_directory = Column(String(500))  # Path to tenant's data folder
    storage_used_bytes = Column(Integer, default=0)
    storage_limit_bytes = Column(Integer, default=1073741824)  # 1GB default

    # Settings
    settings = Column(JSON, default=dict)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    users = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="tenant", cascade="all, delete-orphan")
    connectors = relationship("Connector", back_populates="tenant", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="tenant", cascade="all, delete-orphan")
    knowledge_gaps = relationship("KnowledgeGap", back_populates="tenant", cascade="all, delete-orphan")
    videos = relationship("Video", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tenant {self.slug}>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "plan": self.plan.value,
            "storage_used_bytes": self.storage_used_bytes,
            "storage_limit_bytes": self.storage_limit_bytes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_active": self.is_active
        }


# ============================================================================
# USER MODEL
# ============================================================================

class User(Base):
    """
    User model with secure authentication.
    Users belong to a tenant (organization).
    """
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)

    # Authentication
    email = Column(String(320), nullable=False, index=True)  # Max email length per RFC
    password_hash = Column(String(255), nullable=False)

    # Profile
    full_name = Column(String(255))
    avatar_url = Column(String(500))
    bio = Column(Text)  # User biography/description
    phone = Column(String(20))  # Phone number
    job_title = Column(String(100))  # Job title/position
    department = Column(String(100))  # Department/team
    location = Column(String(255))  # City, Country
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="en")  # ISO 639-1 language code
    date_format = Column(String(20), default="YYYY-MM-DD")  # Preferred date format
    time_format = Column(String(10), default="24h")  # "12h" or "24h"

    # Role & Permissions
    role = Column(Enum(UserRole), default=UserRole.MEMBER, nullable=False)
    permissions = Column(JSON, default=list)  # Additional permissions

    # Security
    email_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    last_login_ip = Column(String(45))  # IPv6 max length
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))

    # MFA (Multi-Factor Authentication)
    mfa_enabled = Column(Boolean, default=False)
    mfa_secret = Column(String(255))  # Encrypted TOTP secret
    mfa_recovery_codes = Column(JSON)  # Encrypted recovery codes

    # Preferences
    preferences = Column(JSON, default=dict)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="users")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    gap_answers = relationship("GapAnswer", back_populates="user", foreign_keys="[GapAnswer.user_id]")

    # Unique email per tenant
    __table_args__ = (
        UniqueConstraint('tenant_id', 'email', name='uq_user_tenant_email'),
        Index('ix_user_email_active', 'email', 'is_active'),
    )

    def __repr__(self):
        return f"<User {self.email}>"

    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "email": self.email,
            "full_name": self.full_name,
            "avatar_url": self.avatar_url,
            "bio": self.bio,
            "phone": self.phone,
            "job_title": self.job_title,
            "department": self.department,
            "location": self.location,
            "timezone": self.timezone,
            "language": self.language,
            "date_format": self.date_format,
            "time_format": self.time_format,
            "role": self.role.value,
            "email_verified": self.email_verified,
            "mfa_enabled": self.mfa_enabled,
            "preferences": self.preferences or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "is_active": self.is_active
        }
        if include_sensitive:
            data["last_login_at"] = self.last_login_at.isoformat() if self.last_login_at else None
            data["failed_login_attempts"] = self.failed_login_attempts
        return data


class UserSession(Base):
    """
    User session tokens for JWT refresh and session management.
    Allows token revocation and multi-device support.
    """
    __tablename__ = "user_sessions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Token info
    refresh_token_hash = Column(String(255), nullable=False, unique=True)
    access_token_jti = Column(String(36))  # JWT ID for access token

    # Session metadata
    device_info = Column(String(500))  # User agent
    ip_address = Column(String(45))
    location = Column(String(255))  # Geolocated

    # Expiration
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    last_used_at = Column(DateTime(timezone=True), default=utc_now)
    is_revoked = Column(Boolean, default=False)
    revoked_at = Column(DateTime(timezone=True))
    revoked_reason = Column(String(255))

    # Relationships
    user = relationship("User", back_populates="sessions")

    def __repr__(self):
        return f"<UserSession {self.id[:8]}...>"


# ============================================================================
# CONNECTOR MODEL (Integrations)
# ============================================================================

class Connector(Base):
    """
    Integration connector for external services (Gmail, Slack, Box, etc.)
    Stores OAuth tokens and sync state per user.
    """
    __tablename__ = "connectors"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)  # Null = org-wide

    # Connector type
    connector_type = Column(Enum(ConnectorType), nullable=False)
    name = Column(String(255))  # User-friendly name (e.g., "Work Gmail")

    # Status
    status = Column(Enum(ConnectorStatus), default=ConnectorStatus.NOT_CONFIGURED)
    error_message = Column(Text)

    # OAuth credentials (encrypted in production)
    access_token = Column(Text)  # Should be encrypted
    refresh_token = Column(Text)  # Should be encrypted
    token_expires_at = Column(DateTime(timezone=True))
    token_scopes = Column(JSON, default=list)

    # Connector-specific settings
    settings = Column(JSON, default=dict)  # E.g., labels, channels, repos

    # Sync state
    last_sync_at = Column(DateTime(timezone=True))
    last_sync_status = Column(String(50))
    last_sync_items_count = Column(Integer, default=0)
    last_sync_error = Column(Text)
    sync_cursor = Column(Text)  # For incremental sync (e.g., historyId, cursor)

    # Statistics
    total_items_synced = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="connectors")
    documents = relationship("Document", back_populates="connector")

    __table_args__ = (
        Index('ix_connector_tenant_type', 'tenant_id', 'connector_type'),
    )

    def __repr__(self):
        return f"<Connector {self.connector_type.value}:{self.id[:8]}>"

    def to_dict(self, include_tokens: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "connector_type": self.connector_type.value,
            "name": self.name,
            "status": self.status.value,
            "error_message": self.error_message,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "total_items_synced": self.total_items_synced,
            "settings": self.settings,
            "is_active": self.is_active
        }
        if include_tokens:
            data["has_access_token"] = bool(self.access_token)
            data["has_refresh_token"] = bool(self.refresh_token)
            data["token_expires_at"] = self.token_expires_at.isoformat() if self.token_expires_at else None
        return data


# ============================================================================
# DOCUMENT MODEL
# ============================================================================

class Document(Base):
    """
    Document model for all ingested content.
    Stores emails, messages, files with classification and embedding info.
    """
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    connector_id = Column(String(36), ForeignKey("connectors.id"), nullable=True)

    # Source identification
    external_id = Column(String(500))  # ID from source system (email ID, message ID)
    source_type = Column(String(50))  # email, message, file, etc.
    source_url = Column(String(2000))  # Original URL if applicable

    # Content
    title = Column(String(500))
    content = Column(Text)  # Full text content
    content_html = Column(Text)  # Original HTML if applicable
    summary = Column(Text)  # AI-generated summary

    # Structured extraction for Knowledge Gap analysis (added 2025-12-09)
    # Contains: summary, key_topics, entities, decisions, processes, dates, action_items
    structured_summary = Column(JSON, nullable=True)
    structured_summary_at = Column(DateTime(timezone=True))  # When extraction was done

    # Metadata
    doc_metadata = Column(JSON, default=dict)  # Source-specific metadata

    # Participants (for emails/messages)
    sender = Column(String(500))
    sender_email = Column(String(320))
    recipients = Column(JSON, default=list)  # List of recipient emails

    # Timestamps from source
    source_created_at = Column(DateTime(timezone=True))
    source_updated_at = Column(DateTime(timezone=True))

    # Classification
    status = Column(Enum(DocumentStatus), default=DocumentStatus.PENDING, index=True)
    classification = Column(Enum(DocumentClassification), default=DocumentClassification.UNKNOWN)
    classification_confidence = Column(Float)  # 0.0 to 1.0
    classification_reason = Column(Text)  # AI explanation
    user_confirmed = Column(Boolean, default=False)
    user_confirmed_at = Column(DateTime(timezone=True))

    # Embedding
    embedding_generated = Column(Boolean, default=False)
    embedding_model = Column(String(100))
    chunk_count = Column(Integer, default=0)
    embedded_at = Column(DateTime(timezone=True))  # When embedded to Pinecone

    # Project assignment
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_deleted = Column(Boolean, default=False)
    deleted_at = Column(DateTime(timezone=True))

    # Relationships
    tenant = relationship("Tenant", back_populates="documents")
    connector = relationship("Connector", back_populates="documents")
    project = relationship("Project", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    __table_args__ = (
        Index('ix_document_tenant_status', 'tenant_id', 'status'),
        Index('ix_document_tenant_classification', 'tenant_id', 'classification'),
        Index('ix_document_external', 'tenant_id', 'connector_id', 'external_id'),
        Index('ix_document_sender', 'tenant_id', 'sender_email'),  # For sender queries
        Index('ix_document_embedded', 'tenant_id', 'embedded_at'),  # For embedding status
        Index('ix_document_confidence', 'classification_confidence'),  # For sorting
        Index('ix_document_created', 'tenant_id', 'created_at'),  # For date-based queries
    )

    def __repr__(self):
        return f"<Document {self.title[:30] if self.title else self.id[:8]}>"

    def to_dict(self, include_content: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "connector_id": self.connector_id,
            "external_id": self.external_id,
            "source_type": self.source_type,
            "title": self.title,
            "summary": self.summary,
            "sender": self.sender,
            "sender_email": self.sender_email,
            "recipients": self.recipients,
            "source_created_at": self.source_created_at.isoformat() if self.source_created_at else None,
            "status": self.status.value,
            "classification": self.classification.value,
            "classification_confidence": self.classification_confidence,
            "classification_reason": self.classification_reason,
            "user_confirmed": self.user_confirmed,
            "project_id": self.project_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_deleted": self.is_deleted,
            "has_structured_summary": self.structured_summary is not None
        }
        if include_content:
            data["content"] = self.content
            data["content_html"] = self.content_html
            data["metadata"] = self.doc_metadata
            data["structured_summary"] = self.structured_summary
        return data


class DocumentChunk(Base):
    """
    Document chunks for embedding and retrieval.
    Each document is split into chunks for vector search.
    """
    __tablename__ = "document_chunks"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)  # Security: direct tenant isolation

    # Chunk content
    chunk_index = Column(Integer, nullable=False)  # Order within document
    content = Column(Text, nullable=False)
    token_count = Column(Integer)

    # Embedding (stored as binary for efficiency)
    embedding = Column(LargeBinary)  # Pickled numpy array
    embedding_model = Column(String(100))
    embedding_dimensions = Column(Integer)

    # Metadata
    chunk_metadata = Column(JSON, default=dict)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint('document_id', 'chunk_index', name='uq_chunk_document_index'),
        Index('ix_chunk_tenant', 'tenant_id'),  # Fast tenant filtering
    )

    def __repr__(self):
        return f"<DocumentChunk {self.document_id[:8]}:{self.chunk_index}>"


# ============================================================================
# PROJECT MODEL
# ============================================================================

class Project(Base):
    """
    Project/Topic cluster for organizing documents.
    Projects are auto-generated via BERTopic or manually created.
    """
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)

    # Project info
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Clustering metadata (if auto-generated)
    topic_id = Column(Integer)  # BERTopic ID
    topic_words = Column(JSON, default=list)  # Top words for topic
    is_auto_generated = Column(Boolean, default=False)

    # Statistics
    document_count = Column(Integer, default=0)
    gap_count = Column(Integer, default=0)

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    is_archived = Column(Boolean, default=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="projects")
    documents = relationship("Document", back_populates="project")
    knowledge_gaps = relationship("KnowledgeGap", back_populates="project")

    def __repr__(self):
        return f"<Project {self.name}>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "name": self.name,
            "description": self.description,
            "topic_words": self.topic_words,
            "is_auto_generated": self.is_auto_generated,
            "document_count": self.document_count,
            "gap_count": self.gap_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_archived": self.is_archived
        }


# ============================================================================
# KNOWLEDGE GAP MODEL
# ============================================================================

class KnowledgeGap(Base):
    """
    Knowledge gap identified by AI analysis.
    Contains questions that need to be answered to fill the gap.
    """
    __tablename__ = "knowledge_gaps"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    # Gap info
    title = Column(String(500), nullable=False)
    description = Column(Text)
    category = Column(Enum(GapCategory), nullable=False)

    # Priority (1-5, 5 being highest)
    priority = Column(Integer, default=3)

    # Status
    status = Column(Enum(GapStatus), default=GapStatus.OPEN, index=True)

    # Questions
    questions = Column(JSON, default=list)  # List of question objects

    # Context (related documents/content that led to identifying this gap)
    context = Column(JSON, default=dict)
    related_document_ids = Column(JSON, default=list)

    # User Feedback (for improving gap detection accuracy)
    feedback_useful = Column(Integer, default=0)  # Count of "useful" votes
    feedback_not_useful = Column(Integer, default=0)  # Count of "not useful" votes
    feedback_comments = Column(JSON, default=list)  # List of feedback comments
    quality_score = Column(Float, default=0.0)  # AI-generated quality score 0-1
    fingerprint = Column(String(32), index=True)  # For deduplication

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    closed_at = Column(DateTime(timezone=True))

    # Relationships
    tenant = relationship("Tenant", back_populates="knowledge_gaps")
    project = relationship("Project", back_populates="knowledge_gaps")
    answers = relationship("GapAnswer", back_populates="knowledge_gap", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<KnowledgeGap {self.title[:30]}>"

    def to_dict(self, include_answers: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "category": self.category.value,
            "priority": self.priority,
            "status": self.status.value,
            "questions": self.questions,
            "context": self.context,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            # Feedback fields
            "feedback_useful": self.feedback_useful or 0,
            "feedback_not_useful": self.feedback_not_useful or 0,
            "quality_score": self.quality_score or 0.0,
            "fingerprint": self.fingerprint,
        }
        if include_answers:
            data["answers"] = [a.to_dict() for a in self.answers]
        return data


class GapAnswer(Base):
    """
    Answer to a knowledge gap question.
    Can be text or transcribed from voice input.
    """
    __tablename__ = "gap_answers"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    knowledge_gap_id = Column(String(36), ForeignKey("knowledge_gaps.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)  # Security: direct tenant isolation
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Question reference
    question_index = Column(Integer)  # Index of question in gap.questions
    question_text = Column(Text)  # Snapshot of question

    # Answer
    answer_text = Column(Text, nullable=False)

    # Voice transcription metadata
    is_voice_transcription = Column(Boolean, default=False)
    audio_file_path = Column(String(500))
    transcription_confidence = Column(Float)
    transcription_model = Column(String(100))  # e.g., "whisper-1"

    # Verification
    is_verified = Column(Boolean, default=False)
    verified_by_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    verified_at = Column(DateTime(timezone=True))

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    knowledge_gap = relationship("KnowledgeGap", back_populates="answers")
    user = relationship("User", back_populates="gap_answers", foreign_keys=[user_id])

    __table_args__ = (
        Index('ix_gap_answer_tenant', 'tenant_id'),  # Fast tenant filtering
    )

    def __repr__(self):
        return f"<GapAnswer {self.id[:8]}>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "knowledge_gap_id": self.knowledge_gap_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "question_index": self.question_index,
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "is_voice_transcription": self.is_voice_transcription,
            "is_verified": self.is_verified,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============================================================================
# VIDEO MODEL
# ============================================================================

class Video(Base):
    """
    Generated training video from knowledge base.
    Tracks generation progress and storage.
    """
    __tablename__ = "videos"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)

    # Video info
    title = Column(String(500), nullable=False)
    description = Column(Text)

    # Generation
    status = Column(Enum(VideoStatus), default=VideoStatus.QUEUED, index=True)
    progress_percent = Column(Integer, default=0)
    current_step = Column(String(200))  # Current generation step
    error_message = Column(Text)

    # Source content
    source_type = Column(String(50))  # pptx, documents, gap_answers
    source_document_ids = Column(JSON, default=list)
    source_config = Column(JSON, default=dict)  # Generation settings

    # Output
    file_path = Column(String(500))
    file_size_bytes = Column(Integer)
    duration_seconds = Column(Float)
    thumbnail_path = Column(String(500))

    # Metadata
    slides_count = Column(Integer)
    voice_model = Column(String(100))

    # Audit
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    # Relationships
    tenant = relationship("Tenant", back_populates="videos")

    def __repr__(self):
        return f"<Video {self.title[:30]}>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "progress_percent": self.progress_percent,
            "current_step": self.current_step,
            "error_message": self.error_message,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "duration_seconds": self.duration_seconds,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


# ============================================================================
# AUDIT LOG MODEL
# ============================================================================

class AuditLog(Base):
    """
    Audit log for tracking all important actions.
    Essential for compliance and debugging.
    """
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)

    # Action
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(50))  # user, document, connector, etc.
    resource_id = Column(String(36))

    # Details
    details = Column(JSON, default=dict)
    old_values = Column(JSON)  # For updates
    new_values = Column(JSON)  # For updates

    # Request context
    ip_address = Column(String(45))
    user_agent = Column(String(500))

    # Timestamp
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    __table_args__ = (
        Index('ix_audit_tenant_action', 'tenant_id', 'action'),
        Index('ix_audit_resource', 'resource_type', 'resource_id'),
    )

    def __repr__(self):
        return f"<AuditLog {self.action}:{self.resource_type}>"


# ============================================================================
# DATABASE ENGINE & SESSION
# ============================================================================

# Create engine
engine = create_engine(
    get_database_url(),
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,  # Verify connections before use
    pool_recycle=3600,  # Recycle connections after 1 hour
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """Get database session (for dependency injection)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# DELETED DOCUMENT TRACKING
# ============================================================================

# ============================================================================
# CHAT HISTORY MODELS
# ============================================================================

class ChatConversation(Base):
    """
    Chat conversation session for storing chat history.
    Each conversation belongs to a tenant and user.
    """
    __tablename__ = "chat_conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)

    # Conversation info
    title = Column(String(255))  # Auto-generated from first message or user-set

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    last_message_at = Column(DateTime(timezone=True), default=utc_now)

    # Status
    is_archived = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)

    # Relationships
    messages = relationship("ChatMessage", back_populates="conversation", cascade="all, delete-orphan", order_by="ChatMessage.created_at")

    __table_args__ = (
        Index('ix_chat_conv_tenant_user', 'tenant_id', 'user_id'),
        Index('ix_chat_conv_last_message', 'tenant_id', 'last_message_at'),
    )

    def __repr__(self):
        return f"<ChatConversation {self.title or self.id[:8]}>"

    def to_dict(self, include_messages: bool = False) -> Dict[str, Any]:
        data = {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "is_archived": self.is_archived,
            "is_pinned": self.is_pinned,
            "message_count": len(self.messages) if self.messages else 0
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages]
        return data


class ChatMessage(Base):
    """
    Individual chat message within a conversation.
    """
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    conversation_id = Column(String(36), ForeignKey("chat_conversations.id"), nullable=False, index=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)  # Redundant but fast for queries

    # Message content
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)

    # Sources for assistant messages
    sources = Column(JSON, default=list)  # Array of source references

    # Extra data (renamed from metadata - reserved in SQLAlchemy)
    extra_data = Column(JSON, default=dict)  # Query type, confidence, etc.

    # Timestamps
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    conversation = relationship("ChatConversation", back_populates="messages")

    __table_args__ = (
        Index('ix_chat_msg_tenant', 'tenant_id'),
        Index('ix_chat_msg_conv_created', 'conversation_id', 'created_at'),
    )

    def __repr__(self):
        return f"<ChatMessage {self.role}:{self.id[:8]}>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "sources": self.sources,
            "metadata": self.extra_data,  # Return as 'metadata' for API compatibility
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


# ============================================================================
# DELETED DOCUMENT TRACKING
# ============================================================================

class DeletedDocument(Base):
    """
    Tracks permanently deleted documents by external_id.
    This prevents sync from re-creating documents the user has deleted.
    """
    __tablename__ = "deleted_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False, index=True)
    connector_id = Column(String(36), ForeignKey("connectors.id"), nullable=True)

    # External identifier from source system (Box file ID, email ID, etc.)
    external_id = Column(String(500), nullable=False)
    source_type = Column(String(50))  # box, gmail, slack, etc.

    # Original document info (for audit trail)
    original_title = Column(String(500))

    # Audit
    deleted_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    deleted_by = Column(String(36))  # User ID who deleted

    __table_args__ = (
        Index('ix_deleted_doc_lookup', 'tenant_id', 'connector_id', 'external_id'),
        UniqueConstraint('tenant_id', 'connector_id', 'external_id', name='uq_deleted_doc'),
    )

    def __repr__(self):
        return f"<DeletedDocument {self.external_id[:20]}>"


def init_database():
    """Initialize database (create tables)"""
    Base.metadata.create_all(bind=engine)
    print("✓ Database tables created successfully")


def drop_database():
    """Drop all tables (use with caution!)"""
    Base.metadata.drop_all(bind=engine)
    print("✓ Database tables dropped")


# ============================================================================
# EVENT LISTENERS
# ============================================================================

@event.listens_for(Tenant, 'before_insert')
def create_tenant_directory(mapper, connection, target):
    """Create data directory for new tenant"""
    if not target.data_directory:
        base_path = Path(__file__).parent.parent / "tenant_data" / target.slug
        target.data_directory = str(base_path)


@event.listens_for(Document, 'after_update')
def update_project_document_count(mapper, connection, target):
    """Update project document count when document changes project"""
    # This would be done in application code or via a trigger
    pass
