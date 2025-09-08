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
                insights = ai_service.analyze_email_content(email)
                
                # Process categorization
                category_result = ai_service.categorize_email(email)
                if category_result:
                    email.category = category_result.get('category')
                    email.confidence_score = category_result.get('confidence', 0.0)
                
                # Process sentiment analysis
                sentiment_result = ai_service.analyze_sentiment(email)
                if sentiment_result:
                    sentiment = SentimentAnalysis(
                        email_id=email.id,
                        sentiment=sentiment_result.get('sentiment'),
                        confidence=sentiment_result.get('confidence', 0.0),
                        emotions=sentiment_result.get('emotions', {}),
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(sentiment)
                
                # Process importance scoring
                importance_score = ai_service.calculate_importance_score(email)
                email.importance_score = importance_score
                
                # Create email insight record
                if insights:
                    insight = EmailInsight(
                        email_id=email.id,
                        user_id=user_id,
                        insight_type='ai_analysis',
                        content=insights,
                        confidence_score=insights.get('confidence', 0.0),
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(insight)
                    insights_created += 1
                
                # Mark as processed
                email.ai_processed = True
                email.ai_processed_at = datetime.now(timezone.utc)
                processed_count += 1
                
            except Exception as e:
                print(f"Error processing AI insights for email {email.id}: {str(e)}")
                continue
        
        db.commit()
        
        # Trigger thread analysis if we processed significant emails
        if processed_count > 0:
            analyze_email_threads.delay(user_id)
        
        return {
            'user_id': user_id,
            'total_emails': len(emails),
            'processed_count': processed_count,
            'insights_created': insights_created,
            'status': 'completed'
        }
        
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@celery_app.task(bind=True, max_retries=2)
def analyze_email_threads(self, user_id: int, thread_ids: Optional[List[int]] = None):
    """
    Analyze email threads for conversation patterns and insights
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Get threads to analyze
        query = db.query(EmailThread).filter(EmailThread.user_id == user_id)
        if thread_ids:
            query = query.filter(EmailThread.id.in_(thread_ids))
        else:
            # Analyze threads updated in last 24 hours
            query = query.filter(
                EmailThread.updated_at >= datetime.now(timezone.utc) - timedelta(hours=24)
            )
        
        threads = query.all()
        
        processed_threads = 0
        insights_created = 0
        
        for thread in threads:
            try:
                # Get thread emails
                thread_emails = db.query(Email).filter(
                    Email.thread_id == thread.id
                ).order_by(Email.received_at).all()
                
                if len(thread_emails) < 2:  # Skip single-email threads
                    continue
                
                # Analyze conversation flow
                conversation_analysis = ai_service.analyze_conversation_thread(thread_emails)
                
                if conversation_analysis:
                    # Update thread with insights
                    thread.ai_insights = conversation_analysis
                    thread.response_pattern = conversation_analysis.get('response_pattern')
                    thread.conversation_tone = conversation_analysis.get('tone')
                    thread.key_topics = conversation_analysis.get('topics', [])
                    
                    # Create thread insight
                    thread_insight = EmailInsight(
                        thread_id=thread.id,
                        user_id=user_id,
                        insight_type='thread_analysis',
                        content=conversation_analysis,
                        confidence_score=conversation_analysis.get('confidence', 0.0),
                        created_at=datetime.now(timezone.utc)
                    )
                    db.add(thread_insight)
                    insights_created += 1
                
                processed_threads += 1
                
            except Exception as e:
                print(f"Error analyzing thread {thread.id}: {str(e)}")
                continue
        
        db.commit()
        
        return {
            'user_id': user_id,
            'processed_threads': processed_threads,
            'insights_created': insights_created,
            'status': 'completed'
        }
        
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

@celery_app.task
def generate_daily_insights(user_id: int, date: Optional[str] = None):
    """
    Generate daily AI insights summary for a user
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Parse date or use yesterday
        if date:
            target_date = datetime.fromisoformat(date).date()
        else:
            target_date = (datetime.now(timezone.utc) - timedelta(days=1)).date()
        
        # Get emails from the target date
        start_date = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        end_date = start_date + timedelta(days=1)
        
        emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.received_at >= start_date,
            Email.received_at < end_date,
            Email.ai_processed == True
        ).all()
        
        if not emails:
            return {
                'user_id': user_id,
                'date': target_date.isoformat(),
                'status': 'no_emails',
                'insights': None
            }
        
        # Generate comprehensive daily insights
        daily_insights = ai_service.generate_daily_summary(emails, target_date)
        
        # Store insights
        insight_record = EmailInsight(
            user_id=user_id,
            insight_type='daily_summary',
            content=daily_insights,
            metadata={'date': target_date.isoformat()},
            confidence_score=daily_insights.get('confidence', 0.8),
            created_at=datetime.now(timezone.utc)
        )
        db.add(insight_record)
        db.commit()
        
        return {
            'user_id': user_id,
            'date': target_date.isoformat(),
            'total_emails': len(emails),
            'insights': daily_insights,
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"Error generating daily insights for user {user_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task
def detect_email_patterns(user_id: int, days_back: int = 30):
    """
    Detect patterns in user's email behavior
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Get emails from the specified period
        start_date = datetime.now(timezone.utc) - timedelta(days=days_back)
        emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.received_at >= start_date,
            Email.ai_processed == True
        ).all()
        
        if len(emails) < 10:  # Need minimum emails for pattern detection
            return {
                'user_id': user_id,
                'status': 'insufficient_data',
                'message': 'Not enough emails for pattern detection'
            }
        
        # Analyze patterns
        patterns = ai_service.detect_communication_patterns(emails)
        
        # Store pattern insights
        if patterns:
            pattern_insight = EmailInsight(
                user_id=user_id,
                insight_type='communication_patterns',
                content=patterns,
                metadata={'analysis_period_days': days_back},
                confidence_score=patterns.get('confidence', 0.7),
                created_at=datetime.now(timezone.utc)
            )
            db.add(pattern_insight)
            db.commit()
        
        return {
            'user_id': user_id,
            'analysis_period_days': days_back,
            'total_emails_analyzed': len(emails),
            'patterns_detected': len(patterns.get('patterns', [])) if patterns else 0,
            'patterns': patterns,
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"Error detecting patterns for user {user_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task(bind=True, max_retries=2)
def classify_email_batch(self, email_ids: List[int]):
    """
    Classify a batch of emails using AI
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        emails = db.query(Email).filter(Email.id.in_(email_ids)).all()
        
        classified_count = 0
        categories_created = 0
        
        for email in emails:
            try:
                # Skip if already classified
                if email.category:
                    continue
                
                # Classify email
                classification = ai_service.categorize_email(email)
                
                if classification:
                    email.category = classification.get('category')
                    email.confidence_score = classification.get('confidence', 0.0)
                    
                    # Create category record if it's a new category
                    category_name = classification.get('category')
                    existing_category = db.query(EmailCategory).filter(
                        EmailCategory.user_id == email.user_id,
                        EmailCategory.name == category_name
                    ).first()
                    
                    if not existing_category:
                        new_category = EmailCategory(
                            user_id=email.user_id,
                            name=category_name,
                            description=classification.get('description', ''),
                            color=classification.get('suggested_color', '#007bff'),
                            created_at=datetime.now(timezone.utc)
                        )
                        db.add(new_category)
                        categories_created += 1
                    
                    classified_count += 1
                
            except Exception as e:
                print(f"Error classifying email {email.id}: {str(e)}")
                continue
        
        db.commit()
        
        return {
            'total_emails': len(emails),
            'classified_count': classified_count,
            'categories_created': categories_created,
            'status': 'completed'
        }
        
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

@celery_app.task
def analyze_sender_relationships(user_id: int):
    """
    Analyze relationships with email senders using AI
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Get all unique senders for the user
        senders_query = db.query(Email.sender).filter(
            Email.user_id == user_id
        ).distinct()
        
        sender_analysis = {}
        
        for sender_row in senders_query:
            sender = sender_row[0]
            if not sender:
                continue
            
            # Get all emails from this sender
            sender_emails = db.query(Email).filter(
                Email.user_id == user_id,
                Email.sender == sender
            ).order_by(Email.received_at).all()
            
            if len(sender_emails) < 3:  # Need minimum emails for analysis
                continue
            
            # Analyze relationship
            relationship_analysis = ai_service.analyze_sender_relationship(sender_emails)
            
            if relationship_analysis:
                sender_analysis[sender] = relationship_analysis
        
        # Store relationship insights
        if sender_analysis:
            relationship_insight = EmailInsight(
                user_id=user_id,
                insight_type='sender_relationships',
                content={'relationships': sender_analysis},
                confidence_score=0.8,
                created_at=datetime.now(timezone.utc)
            )
            db.add(relationship_insight)
            db.commit()
        
        return {
            'user_id': user_id,
            'analyzed_senders': len(sender_analysis),
            'total_relationships': len(sender_analysis),
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"Error analyzing sender relationships for user {user_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task
def generate_weekly_insights(user_id: int, week_start: Optional[str] = None):
    """
    Generate weekly AI insights report
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Calculate week range
        if week_start:
            start_date = datetime.fromisoformat(week_start).replace(tzinfo=timezone.utc)
        else:
            # Last complete week (Monday to Sunday)
            today = datetime.now(timezone.utc)
            days_since_monday = today.weekday()
            last_monday = today - timedelta(days=days_since_monday + 7)
            start_date = last_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        
        end_date = start_date + timedelta(days=7)
        
        # Get week's emails
        emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.received_at >= start_date,
            Email.received_at < end_date,
            Email.ai_processed == True
        ).all()
        
        if not emails:
            return {
                'user_id': user_id,
                'week_start': start_date.date().isoformat(),
                'status': 'no_emails'
            }
        
        # Generate weekly insights
        weekly_insights = ai_service.generate_weekly_summary(emails, start_date.date())
        
        # Store insights
        insight_record = EmailInsight(
            user_id=user_id,
            insight_type='weekly_summary',
            content=weekly_insights,
            metadata={
                'week_start': start_date.date().isoformat(),
                'week_end': (end_date - timedelta(days=1)).date().isoformat()
            },
            confidence_score=weekly_insights.get('confidence', 0.8),
            created_at=datetime.now(timezone.utc)
        )
        db.add(insight_record)
        db.commit()
        
        return {
            'user_id': user_id,
            'week_start': start_date.date().isoformat(),
            'total_emails': len(emails),
            'insights': weekly_insights,
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"Error generating weekly insights for user {user_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task
def ai_health_check():
    """
    Health check for AI analysis tasks
    """
    try:
        db = next(get_db())
        ai_service = AIService(db)
        
        # Test AI service connectivity
        test_result = ai_service.health_check()
        
        return {
            'status': 'healthy',
            'ai_service_status': test_result.get('status', 'unknown'),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'queue': 'ai_analysis'
        }
        
    except Exception as e:
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'queue': 'ai_analysis'
        }

# Periodic tasks for AI analysis
celery_app.conf.beat_schedule.update({
    'generate-daily-insights': {
        'task': 'app.tasks.ai_analysis.generate_daily_insights',
        'schedule': 86400.0,  # Run daily at midnight
        'kwargs': {'date': None}  # Will use yesterday
    },
    'detect-weekly-patterns': {
        'task': 'app.tasks.ai_analysis.detect_email_patterns',
        'schedule': 604800.0,  # Run weekly
        'kwargs': {'days_back': 30}
    },
    'analyze-sender-relationships': {
        'task': 'app.tasks.ai_analysis.analyze_sender_relationships',
        'schedule': 259200.0,  # Run every 3 days
    },
    'ai-health-check': {
        'task': 'app.tasks.ai_analysis.ai_health_check',
        'schedule': 300.0,  # Run every 5 minutes
    }
})
