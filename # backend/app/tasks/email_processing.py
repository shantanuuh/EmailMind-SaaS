"""
Email Processing Tasks - Celery tasks for email ingestion and processing
"""
from celery import Celery
from typing import List, Dict, Any, Optional
import asyncio
from datetime import datetime, timezone
import json
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.email import Email, EmailThread
from app.services.email_service import EmailService
from app.services.ai_service import AIService
from app.tasks.ai_analysis import process_ai_insights

# Initialize Celery
celery_app = Celery(
    'emailmind_tasks',
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_routes={
        'app.tasks.email_processing.*': {'queue': 'email_processing'},
        'app.tasks.ai_analysis.*': {'queue': 'ai_analysis'},
        'app.tasks.cleanup.*': {'queue': 'cleanup'}
    }
)

@celery_app.task(bind=True, max_retries=3)
def sync_user_emails(self, user_id: int, provider: str = "gmail", full_sync: bool = False):
    """
    Sync emails for a specific user from their email provider
    """
    try:
        db = next(get_db())
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user:
            raise Exception(f"User {user_id} not found")
        
        email_service = EmailService(db)
        
        # Get emails from provider
        if provider == "gmail":
            emails_data = email_service.fetch_gmail_emails(user, full_sync=full_sync)
        elif provider == "outlook":
            emails_data = email_service.fetch_outlook_emails(user, full_sync=full_sync)
        else:
            emails_data = email_service.fetch_imap_emails(user, full_sync=full_sync)
        
        # Process emails in batches
        batch_size = 50
        processed_count = 0
        
        for i in range(0, len(emails_data), batch_size):
            batch = emails_data[i:i + batch_size]
            
            # Process batch
            process_email_batch.delay(user_id, batch, provider)
            processed_count += len(batch)
        
        # Update user's last sync time
        user.last_email_sync = datetime.now(timezone.utc)
        db.commit()
        
        return {
            'user_id': user_id,
            'total_emails': len(emails_data),
            'processed_batches': (len(emails_data) + batch_size - 1) // batch_size,
            'status': 'completed'
        }
        
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@celery_app.task(bind=True, max_retries=2)
def process_email_batch(self, user_id: int, emails_data: List[Dict[str, Any]], provider: str):
    """
    Process a batch of emails - store in database and trigger AI analysis
    """
    try:
        db = next(get_db())
        email_service = EmailService(db)
        
        processed_emails = []
        
        for email_data in emails_data:
            try:
                # Check if email already exists
                existing_email = db.query(Email).filter(
                    Email.user_id == user_id,
                    Email.message_id == email_data.get('message_id')
                ).first()
                
                if existing_email:
                    continue
                
                # Create email record
                email = Email(
                    user_id=user_id,
                    message_id=email_data.get('message_id'),
                    subject=email_data.get('subject', ''),
                    sender=email_data.get('sender', ''),
                    recipient=email_data.get('recipient', ''),
                    cc=email_data.get('cc', []),
                    bcc=email_data.get('bcc', []),
                    body_text=email_data.get('body_text', ''),
                    body_html=email_data.get('body_html', ''),
                    received_at=email_data.get('received_at', datetime.now(timezone.utc)),
                    is_read=email_data.get('is_read', False),
                    is_important=email_data.get('is_important', False),
                    labels=email_data.get('labels', []),
                    provider_data=email_data.get('provider_data', {}),
                    created_at=datetime.now(timezone.utc)
                )
                
                db.add(email)
                db.flush()  # Get the email ID without committing
                
                # Handle threading
                thread_id = email_data.get('thread_id')
                if thread_id:
                    thread = db.query(EmailThread).filter(
                        EmailThread.user_id == user_id,
                        EmailThread.provider_thread_id == thread_id
                    ).first()
                    
                    if not thread:
                        thread = EmailThread(
                            user_id=user_id,
                            provider_thread_id=thread_id,
                            subject=email.subject,
                            participants=[email.sender, email.recipient] + email.cc + email.bcc,
                            created_at=datetime.now(timezone.utc),
                            updated_at=datetime.now(timezone.utc)
                        )
                        db.add(thread)
                        db.flush()
                    
                    email.thread_id = thread.id
                
                processed_emails.append(email.id)
                
            except Exception as e:
                print(f"Error processing email {email_data.get('message_id', 'unknown')}: {str(e)}")
                continue
        
        db.commit()
        
        # Trigger AI analysis for processed emails
        if processed_emails:
            process_ai_insights.delay(user_id, processed_emails)
        
        return {
            'user_id': user_id,
            'processed_count': len(processed_emails),
            'total_batch_size': len(emails_data),
            'status': 'completed'
        }
        
    except Exception as exc:
        db.rollback()
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

@celery_app.task
def incremental_email_sync():
    """
    Periodic task to sync new emails for all active users
    """
    try:
        db = next(get_db())
        
        # Get users who have email sync enabled and haven't synced recently
        active_users = db.query(User).filter(
            User.is_active == True,
            User.email_sync_enabled == True
        ).all()
        
        synced_users = []
        
        for user in active_users:
            # Check if user needs sync (hasn't synced in last hour)
            if (not user.last_email_sync or 
                (datetime.now(timezone.utc) - user.last_email_sync).seconds > 3600):
                
                # Determine provider based on user's email domain or settings
                provider = user.email_provider or "gmail"
                
                # Queue sync task
                sync_user_emails.delay(user.id, provider, full_sync=False)
                synced_users.append(user.id)
        
        return {
            'total_active_users': len(active_users),
            'synced_users': len(synced_users),
            'user_ids': synced_users,
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"Error in incremental email sync: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task(bind=True, max_retries=2)
def process_new_email(self, user_id: int, email_data: Dict[str, Any]):
    """
    Process a single new email (for real-time processing via webhooks)
    """
    try:
        db = next(get_db())
        
        # Process the email
        result = process_email_batch(user_id, [email_data], email_data.get('provider', 'gmail'))
        
        # If processing successful, update real-time stats
        if result.get('status') == 'completed':
            update_user_email_stats.delay(user_id)
        
        return result
        
    except Exception as exc:
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries))

@celery_app.task
def update_user_email_stats(user_id: int):
    """
    Update user's email statistics after processing new emails
    """
    try:
        db = next(get_db())
        
        # Calculate basic stats
        total_emails = db.query(Email).filter(Email.user_id == user_id).count()
        unread_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.is_read == False
        ).count()
        important_emails = db.query(Email).filter(
            Email.user_id == user_id,
            Email.is_important == True
        ).count()
        
        # Update user stats (you might want to create a UserStats model)
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            # Store in user metadata or separate stats table
            user.metadata = user.metadata or {}
            user.metadata.update({
                'total_emails': total_emails,
                'unread_emails': unread_emails,
                'important_emails': important_emails,
                'last_stats_update': datetime.now(timezone.utc).isoformat()
            })
            db.commit()
        
        return {
            'user_id': user_id,
            'total_emails': total_emails,
            'unread_emails': unread_emails,
            'important_emails': important_emails
        }
        
    except Exception as e:
        print(f"Error updating user stats for {user_id}: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task
def bulk_email_sync(user_ids: List[int], provider: str = "gmail"):
    """
    Sync emails for multiple users (useful for admin operations)
    """
    try:
        results = []
        
        for user_id in user_ids:
            task_result = sync_user_emails.delay(user_id, provider, full_sync=True)
            results.append({
                'user_id': user_id,
                'task_id': task_result.id
            })
        
        return {
            'total_users': len(user_ids),
            'queued_tasks': len(results),
            'tasks': results,
            'status': 'queued'
        }
        
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@celery_app.task
def reprocess_failed_emails(user_id: Optional[int] = None, hours_back: int = 24):
    """
    Reprocess emails that failed during initial processing
    """
    try:
        db = next(get_db())
        
        # Query for emails that might have failed processing
        # (you might need to add a 'processing_status' field to Email model)
        query = db.query(Email).filter(
            Email.ai_processed == False,
            Email.created_at >= datetime.now(timezone.utc) - timedelta(hours=hours_back)
        )
        
        if user_id:
            query = query.filter(Email.user_id == user_id)
        
        failed_emails = query.all()
        
        # Group by user for batch processing
        user_emails = {}
        for email in failed_emails:
            if email.user_id not in user_emails:
                user_emails[email.user_id] = []
            user_emails[email.user_id].append(email.id)
        
        # Queue reprocessing tasks
        reprocessed_count = 0
        for uid, email_ids in user_emails.items():
            process_ai_insights.delay(uid, email_ids)
            reprocessed_count += len(email_ids)
        
        return {
            'total_failed_emails': len(failed_emails),
            'affected_users': len(user_emails),
            'reprocessed_count': reprocessed_count,
            'status': 'completed'
        }
        
    except Exception as e:
        print(f"Error reprocessing failed emails: {str(e)}")
        return {'status': 'error', 'message': str(e)}

@celery_app.task
def health_check():
    """
    Health check task to verify the task queue is working
    """
    return {
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'queue': 'email_processing'
    }

# Periodic tasks configuration
celery_app.conf.beat_schedule = {
    'incremental-email-sync': {
        'task': 'app.tasks.email_processing.incremental_email_sync',
        'schedule': 3600.0,  # Run every hour
    },
    'reprocess-failed-emails': {
        'task': 'app.tasks.email_processing.reprocess_failed_emails',
        'schedule': 86400.0,  # Run daily
    },
    'health-check': {
        'task': 'app.tasks.email_processing.health_check',
        'schedule': 300.0,  # Run every 5 minutes
    },
}
