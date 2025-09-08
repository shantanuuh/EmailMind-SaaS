# backend/app/models/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Float
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base
import enum

class SubscriptionTier(enum.Enum):
    STARTER = "starter"
    PROFESSIONAL = "professional" 
    ENTERPRISE = "enterprise"
    FREE_TRIAL = "free_trial"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Subscription Info
    subscription_tier = Column(Enum(SubscriptionTier), default=SubscriptionTier.FREE_TRIAL)
    stripe_customer_id = Column(String, nullable=True)
    subscription_end_date = Column(DateTime, nullable=True)
    
    # Usage Tracking
    emails_processed = Column(Integer, default=0)
    api_calls_this_month = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    email_accounts = relationship("EmailAccount", back_populates="user", cascade="all, delete-orphan")
    analytics = relationship("EmailAnalytics", back_populates="user", cascade="all, delete-orphan")
