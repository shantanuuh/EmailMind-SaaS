# backend/app/models/analytics.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base

class EmailAnalytics(Base):
    __tablename__ = "email_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Time Period
    date = Column(DateTime, index=True)  # Daily analytics
    period_type = Column(String)  # daily, weekly, monthly
    
    # Volume Metrics
    total_emails_received = Column(Integer, default=0)
    total_emails_sent = Column(Integer, default=0)
    unread_count = Column(Integer, default=0)
    
    # Category Breakdown
    work_emails = Column(Integer, default=0)
    personal_emails = Column(Integer, default=0)
    promotional_emails = Column(Integer, default=0)
    social_emails = Column(Integer, default=0)
    spam_emails = Column(Integer, default=0)
    
    # Engagement Metrics
    emails_read = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)
    emails_forwarded = Column(Integer, default=0)
    emails_deleted = Column(Integer, default=0)
    emails_archived = Column(Integer, default=0)
    
    # Time-based Analysis
    peak_hour = Column(Integer)  # Hour of day with most activity
    response_time_avg_minutes = Column(Float)
    
    # Top Senders Analysis
    top_senders = Column(JSON)  # [{"email": "...", "count": 123}, ...]
    new_senders = Column(Integer, default=0)
    
    # AI Insights
    sentiment_positive = Column(Integer, default=0)
    sentiment_negative = Column(Integer, default=0)
    sentiment_neutral = Column(Integer, default=0)
    avg_importance_score = Column(Float)
    
    # Action Items
    total_action_items = Column(Integer, default=0)
    completed_action_items = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="analytics")

class SenderAnalytics(Base):
    __tablename__ = "sender_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    sender_email = Column(String, index=True, nullable=False)
    sender_name = Column(String)
    sender_domain = Column(String, index=True)
    
    # Volume Metrics
    total_emails_received = Column(Integer, default=0)
    emails_this_month = Column(Integer, default=0)
    emails_this_week = Column(Integer, default=0)
    
    # Engagement
    emails_read = Column(Integer, default=0)
    emails_replied = Column(Integer, default=0)
    avg_response_time_hours = Column(Float)
    
    # AI Analysis
    relationship_type = Column(String)  # colleague, friend, service, promotional
    importance_level = Column(String)  # high, medium, low
    avg_sentiment_score = Column(Float)
    common_topics = Column(JSON)
    
    # Recommendations
    suggested_action = Column(String)  # unsubscribe, prioritize, archive_old
    confidence_score = Column(Float)
    
    first_email_date = Column(DateTime)
    last_email_date = Column(DateTime)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    user = relationship("User")
