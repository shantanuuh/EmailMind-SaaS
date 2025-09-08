"""
AI Analysis Tasks - Celery tasks for AI-powered email analysis
"""
from celery import Celery
from typing import List, Dict, Any, Optional
import json
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.email import Email, EmailThread
from app.models.analytics import EmailInsight, SentimentAnalysis, EmailCategory
from app.services.ai_service import AIService
from app.tasks.email_processing import celery_app

@celery_app.task(bind=True, max_retries=3)
def process_ai_insights(self, user_id: int, email_ids: List[int]):
    """
    Process AI insights for a batch of emails
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Get emails to process
        emails = db.query(Email).filter(
            Email.id.in_(email_ids),
            Email.user_id == user_id
        ).all()
        
        if not emails:
            return {'status': 'no_emails_found', 'user_id': user_id}
        
        processed_count = 0
        insights_created = 0
        
        for email in emails:
            try:
                # Skip if already processed
                if email.ai_processed:
                    continue
                
                # Generate AI insights
                insights = await ai_
