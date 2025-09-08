#backend/app/services/email_service.py
import asyncio
import email
import imaplib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import base64
import json
import re
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
import requests
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..models.email import Email
from ..models.user import User
from ..core.ai_engine import ai_engine
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.gmail_scopes = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.modify'
        ]
    
    async def connect_gmail(self, user_id: int, auth_code: str) -> Dict[str, Any]:
        """Connect Gmail account using OAuth2"""
        try:
            # This would typically involve OAuth2 flow
            # Simplified for demonstration
            return {
                "success": True,
                "provider": "gmail",
                "user_id": user_id,
                "connected_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Gmail connection failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def connect_outlook(self, user_id: int, auth_code: str) -> Dict[str, Any]:
        """Connect Outlook account using Microsoft Graph API"""
        try:
            # Microsoft Graph API integration
            return {
                "success": True,
                "provider": "outlook",
                "user_id": user_id,
                "connected_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Outlook connection failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def connect_imap(self, user_id: int, imap_config: Dict) -> Dict[str, Any]:
        """Connect generic IMAP account"""
        try:
            server = imap_config.get("server")
            port = imap_config.get("port", 993)
            email_addr = imap_config.get("email")
            password = imap_config.get("password")
            
            # Test connection
            mail = imaplib.IMAP4_SSL(server, port)
            mail.login(email_addr, password)
            mail.select("inbox")
            mail.logout()
            
            return {
                "success": True,
                "provider": "imap",
                "user_id": user_id,
                "server": server,
                "connected_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"IMAP connection failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def fetch_gmail_emails(self, credentials: Dict, max_results: int = 100) -> List[Dict]:
        """Fetch emails from Gmail"""
        try:
            # Build Gmail service
            creds = Credentials.from_authorized_user_info(credentials)
            service = build('gmail', 'v1', credentials=creds)
            
            # Get message list
            results = service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q='in:inbox'
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for message in messages:
                msg = service.users().messages().get(
                    userId='me',
                    id=message['id'],
                    format='full'
                ).execute()
                
                email_data = await self._parse_gmail_message(msg)
                if email_data:
                    emails.append(email_data)
            
            return emails
            
        except Exception as e:
            logger.error(f"Gmail fetch failed: {e}")
            return []
    
    async def fetch_imap_emails(self, imap_config: Dict, max_results: int = 100) -> List[Dict]:
        """Fetch emails using IMAP"""
        try:
            server = imap_config.get("server")
            port = imap_config.get("port", 993)
            email_addr = imap_config.get("email")
            password = imap_config.get("password")
            
            mail = imaplib.IMAP4_SSL(server, port)
            mail.login(email_addr, password)
            mail.select("inbox")
            
            # Search for emails
            status, messages = mail.search(None, 'ALL')
            email_ids = messages[0].split()[-max_results:]  # Get latest emails
            
            emails = []
            for email_id in email_ids:
                status, msg_data = mail.fetch(email_id, '(RFC822)')
                msg = email.message_from_bytes(msg_data[0][1])
                
                email_data = await self._parse_email_message(msg)
                if email_data:
                    emails.append(email_data)
            
            mail.logout()
            return emails
            
        except Exception as e:
            logger.error(f"IMAP fetch failed: {e}")
            return []
    
    async def _parse_gmail_message(self, msg: Dict) -> Optional[Dict]:
        """Parse Gmail API message format"""
        try:
            headers = {h['name']: h['value'] for h in msg['payload']['headers']}
            
            # Extract body
            body = ""
            if 'parts' in msg['payload']:
                for part in msg['payload']['parts']:
                    if part['mimeType'] == 'text/plain':
                        body = base64.urlsafe_b64decode(
                            part['body']['data'].encode('ASCII')
                        ).decode('utf-8')
                        break
            else:
                if msg['payload']['mimeType'] == 'text/plain':
                    body = base64.urlsafe_b64decode(
                        msg['payload']['body']['data'].encode('ASCII')
                    ).decode('utf-8')
            
            return {
                "message_id": msg['id'],
                "thread_id": msg['threadId'],
                "sender": headers.get('From', ''),
                "recipient": headers.get('To', ''),
                "subject": headers.get('Subject', ''),
                "body": body,
                "date": headers.get('Date', ''),
                "labels": msg.get('labelIds', []),
                "snippet": msg.get('snippet', ''),
                "has_attachments": len(msg['payload'].get('parts', [])) > 1
            }
            
        except Exception as e:
            logger.error(f"Gmail message parsing failed: {e}")
            return None
    
    async def _parse_email_message(self, msg: email.message.Message) -> Optional[Dict]:
        """Parse standard email message"""
        try:
            # Extract body
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_payload(decode=True).decode('utf-8')
                        break
            else:
                body = msg.get_payload(decode=True).decode('utf-8')
            
            return {
                "message_id": msg.get('Message-ID', ''),
                "sender": msg.get('From', ''),
                "recipient": msg.get('To', ''),
                "subject": msg.get('Subject', ''),
                "body": body,
                "date": msg.get('Date', ''),
                "has_attachments": len([p for p in msg.walk() if p.get_content_disposition() == 'attachment']) > 0
            }
            
        except Exception as e:
            logger.error(f"Email message parsing failed: {e}")
            return None
    
    async def process_emails(self, user_id: int, emails: List[Dict]) -> List[Dict]:
        """Process emails with AI analysis"""
        processed_emails = []
        
        for email_data in emails:
            try:
                # AI Classification
                classification = await ai_engine.classify_email(
                    email_data.get("body", ""),
                    email_data.get("subject", "")
                )
                
                # Sentiment Analysis
                sentiment = await ai_engine.analyze_sentiment(
                    email_data.get("body", "")
                )
                
                # Importance Score
                importance = await ai_engine.calculate_importance_score(email_data)
                
                # Combine all data
                processed_email = {
                    **email_data,
                    "user_id": user_id,
                    "category": classification.get("category"),
                    "category_confidence": classification.get("confidence"),
                    "sentiment": sentiment.get("sentiment"),
                    "sentiment_confidence": sentiment.get("confidence"),
                    "importance_score": importance,
                    "processed_at": datetime.utcnow().isoformat()
                }
                
                processed_emails.append(processed_email)
                
            except Exception as e:
                logger.error(f"Email processing failed: {e}")
                continue
        
        return processed_emails
    
    async def store_emails(self, db: Session, processed_emails: List[Dict]) -> List[int]:
        """Store processed emails in database"""
        stored_ids = []
        
        try:
            for email_data in processed_emails:
                # Check if email already exists
                existing = db.query(Email).filter(
                    Email.message_id == email_data.get("message_id"),
                    Email.user_id == email_data.get("user_id")
                ).first()
                
                if existing:
                    continue
                
                # Create new email record
                email_record = Email(
                    user_id=email_data.get("user_id"),
                    message_id=email_data.get("message_id"),
                    sender=email_data.get("sender"),
                    recipient=email_data.get("recipient"),
                    subject=email_data.get("subject"),
                    body=email_data.get("body"),
                    category=email_data.get("category"),
                    sentiment=email_data.get("sentiment"),
                    importance_score=email_data.get("importance_score"),
                    has_attachments=email_data.get("has_attachments", False),
                    processed_at=datetime.utcnow()
                )
                
                db.add(email_record)
                db.flush()
                stored_ids.append(email_record.id)
            
            db.commit()
            return stored_ids
            
        except Exception as e:
            logger.error(f"Email storage failed: {e}")
            db.rollback()
            return []
    
    async def get_user_emails(
        self, 
        db: Session, 
        user_id: int, 
        skip: int = 0, 
        limit: int = 100,
        category: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> List[Email]:
        """Get user emails with filtering"""
        try:
            query = db.query(Email).filter(Email.user_id == user_id)
            
            if category:
                query = query.filter(Email.category == category)
            
            if date_from:
                query = query.filter(Email.created_at >= date_from)
            
            if date_to:
                query = query.filter(Email.created_at <= date_to)
            
            return query.offset(skip).limit(limit).all()
            
        except Exception as e:
            logger.error(f"Email retrieval failed: {e}")
            return []
    
    async def mark_email_read(self, db: Session, email_id: int, user_id: int) -> bool:
        """Mark email as read"""
        try:
            email_record = db.query(Email).filter(
                Email.id == email_id,
                Email.user_id == user_id
            ).first()
            
            if email_record:
                email_record.is_read = True
                email_record.read_at = datetime.utcnow()
                db.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Mark email read failed: {e}")
            db.rollback()
            return False
    
    async def delete_email(self, db: Session, email_id: int, user_id: int) -> bool:
        """Delete email"""
        try:
            email_record = db.query(Email).filter(
                Email.id == email_id,
                Email.user_id == user_id
            ).first()
            
            if email_record:
                db.delete(email_record)
                db.commit()
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Email deletion failed: {e}")
            db.rollback()
            return False
    
    async def search_emails(
        self, 
        db: Session, 
        user_id: int, 
        query: str,
        limit: int = 50
    ) -> List[Email]:
        """Search emails using full-text search"""
        try:
            # Simple text search (would use Elasticsearch in production)
            search_query = db.query(Email).filter(
                Email.user_id == user_id,
                Email.subject.contains(query) | Email.body.contains(query)
            ).limit(limit)
            
            return search_query.all()
            
        except Exception as e:
            logger.error(f"Email search failed: {e}")
            return []
    
    async def sync_user_emails(self, user_id: int) -> Dict[str, Any]:
        """Sync all connected email accounts for a user"""
        try:
            db = next(get_db())
            user = db.query(User).filter(User.id == user_id).first()
            
            if not user:
                return {"success": False, "error": "User not found"}
            
            total_synced = 0
            sync_results = []
            
            # Get user's connected accounts (would be stored in database)
            # For demo, we'll simulate
            connected_accounts = []  # Would fetch from user settings
            
            for account in connected_accounts:
                if account["provider"] == "gmail":
                    emails = await self.fetch_gmail_emails(account["credentials"])
                elif account["provider"] == "imap":
                    emails = await self.fetch_imap_emails(account["config"])
                else:
                    continue
                
                processed_emails = await self.process_emails(user_id, emails)
                stored_ids = await self.store_emails(db, processed_emails)
                
                total_synced += len(stored_ids)
                sync_results.append({
                    "provider": account["provider"],
                    "emails_synced": len(stored_ids),
                    "success": True
                })
            
            return {
                "success": True,
                "total_synced": total_synced,
                "sync_results": sync_results,
                "synced_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Email sync failed: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
email_service = EmailService()
