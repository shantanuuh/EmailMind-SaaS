# backend/app/models/email.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base
import enum

class EmailProvider(enum.Enum):
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    IMAP = "imap"

class EmailAccount(Base):
    __tablename__ = "email_accounts"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    provider = Column(String)  # gmail, outlook, imap
    email_address = Column(String, nullable=False)
    display_name = Column(String)
    
    # OAuth Tokens (encrypted in production)
    access_token = Column(Text)
    refresh_token = Column(Text)
    token_expires_at = Column(DateTime)
    
    # IMAP Settings
    imap_server = Column(String)
    imap_port = Column(Integer)
    imap_username = Column(String)
    imap_password = Column(Text)  # encrypted
    
    # Sync Settings
    is_active = Column(Boolean, default=True)
    last_sync_at = Column(DateTime)
    sync_from_date = Column(DateTime)
    
    # Stats
    total_emails = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="email_accounts")
    emails = relationship("Email", back_populates="email_account", cascade="all, delete-orphan")

class Email(Base):
    __tablename__ = "emails"
    
    id = Column(Integer, primary_key=True, index=True)
    email_account_id = Column(Integer, ForeignKey("email_accounts.id"), nullable=False)
    
    # Email Identifiers
    message_id = Column(String, unique=True, index=True)
    thread_id = Column(String, index=True)
    
    # Email Content
    subject = Column(Text)
    sender_email = Column(String, index=True)
    sender_name = Column(String)
    recipient_emails = Column(JSON)  # List of recipients
    cc_emails = Column(JSON)
    bcc_emails = Column(JSON)
    
    body_text = Column(Text)
    body_html = Column(Text)
    snippet = Column(Text)  # Short preview
    
    # Metadata
    sent_date = Column(DateTime, index=True)
    received_date = Column(DateTime, index=True)
    labels = Column(JSON)  # Gmail labels or folder names
    importance = Column(String)  # high, normal, low
    
    # Flags
    is_read = Column(Boolean, default=False)
    is_replied = Column(Boolean, default=False)
    is_forwarded = Column(Boolean, default=False)
    has_attachments = Column(Boolean, default=False)
    
    # AI Analysis Results
    ai_category = Column(String)  # work, personal, promotional, social, etc.
    ai_importance_score = Column(Float)  # 0.0 to 1.0
    ai_sentiment = Column(String)  # positive, negative, neutral
    ai_sentiment_score = Column(Float)  # -1.0 to 1.0
    ai_summary = Column(Text)
    ai_action_items = Column(JSON)
    
    # Processing Status
    is_processed = Column(Boolean, default=False)
    processing_error = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    email_account = relationship("EmailAccount", back_populates="emails")
    attachments = relationship("EmailAttachment", back_populates="email", cascade="all, delete-orphan")

class EmailAttachment(Base):
    __tablename__ = "email_attachments"
    
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id"), nullable=False)
    
    filename = Column(String, nullable=False)
    content_type = Column(String)
    size_bytes = Column(Integer)
    file_path = Column(String)  # S3 path or local path
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    email = relationship("Email", back_populates="attachments")
