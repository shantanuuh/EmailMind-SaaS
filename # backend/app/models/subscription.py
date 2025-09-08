# backend/app/models/subscription.py
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, JSON
from sqlalchemy.sql import func
from ..core.database import Base
import enum

class SubscriptionStatus(enum.Enum):
    ACTIVE = "active"
    CANCELED = "canceled"
    PAST_DUE = "past_due"
    TRIALING = "trialing"

class Subscription(Base):
    __tablename__ = "subscriptions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, unique=True)
    
    # Stripe Integration
    stripe_subscription_id = Column(String, unique=True)
    stripe_customer_id = Column(String)
    stripe_price_id = Column(String)
    
    # Subscription Details
    status = Column(String)  # active, canceled, past_due, trialing
    tier = Column(String)    # starter, professional, enterprise
    
    # Billing
    amount = Column(Float)   # Amount in cents
    currency = Column(String, default="usd")
    billing_cycle = Column(String)  # monthly, yearly
    
    # Dates
    current_period_start = Column(DateTime)
    current_period_end = Column(DateTime)
    trial_start = Column(DateTime)
    trial_end = Column(DateTime)
    canceled_at = Column(DateTime)
    
    # Usage Limits
    email_limit = Column(Integer)
    api_limit = Column(Integer)
    
    # Usage This Period
    emails_processed_this_period = Column(Integer, default=0)
    api_calls_this_period = Column(Integer, default=0)
    
    # Features
    features = Column(JSON)  # {"ai_insights": true, "custom_rules": false, ...}
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
