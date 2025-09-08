import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_
from ..core.database import get_db
from ..models.email import Email
from ..models.analytics import EmailAnalytics, AIInsight
from ..models.user import User
import pandas as pd
from collections import defaultdict, Counter
import logging

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self):
        self.cache_ttl = 300  # 5 minutes cache
        self._cache = {}
    
    async def get_email_volume_analytics(
        self, 
        user_id: int, 
        start_date: datetime, 
        end_date: datetime,
        granularity: str = "daily"
    ) -> Dict[str, Any]:
        """Get email volume analytics over time"""
        try:
            db = next(get_db())
            
            # Base query
            query = db.query(Email).filter(
                Email.user_id == user_id,
                Email.created_at >= start_date,
                Email.created_at <= end_date
            )
            
            emails = query.all()
            
            if not emails:
                return {
                    "total_emails": 0,
                    "time_series": [],
                    "average_per_day": 0,
                    "peak_day": None
                }
            
            # Group by time period
            time_groups = defaultdict(int)
            
            for email in emails:
                if granularity == "daily":
                    key = email.created_at.date().isoformat()
                elif granularity == "weekly":
                    # Get Monday of the week
                    monday = email.created_at.date() - timedelta(days=email.created_at.weekday())
                    key = monday.isoformat()
                elif granularity == "monthly":
                    key = email.created_at.strftime("%Y-%m")
                else:
                    key = email.created_at.date().isoformat()
                
                time_groups[key] += 1
            
            # Convert to time series
            time_series = [
                {"date": date, "count": count}
                for date, count in sorted(time_groups.items())
            ]
            
            # Calculate metrics
            total_emails = len(emails)
            days_diff = (end_date - start_date).days or 1
            average_per_day = total_emails / days_diff
            
            peak_day = max(time_groups.items(), key=lambda x: x[1]) if time_groups else None
            
            return {
                "total_emails": total_emails,
                "time_series": time_series,
                "average_per_day": round(average_per_day, 2),
                "peak_day": {
                    "date": peak_day[0],
                    "count": peak_day[1]
                } if peak_day else None
            }
            
        except Exception as e:
            logger.error(f"Email volume analytics failed: {e}")
            return {"error": str(e)}
    
    async def get_sender_analytics(
        self, 
        user_id: int, 
        start_date: datetime, 
        end_date: datetime,
        limit: int = 20
    ) -> Dict[str, Any]:
        """Get sender-based analytics"""
        try:
            db = next(get_db())
            
            emails = db.query(Email).filter(
                Email.user_id == user_id,
                Email.created_at >= start_date,
                Email.created_at <= end_date
            ).all()
            
            if not emails:
                return {"top_senders": [], "sender_categories": {}}
            
            # Count emails by sender
            sender_counts = Counter(email.sender for email in emails)
            sender_stats = {}
            
            for sender, count in sender_counts.items():
                sender_emails = [e for e in emails if e.sender == sender]
                
                # Calculate metrics for this sender
                opened_count = sum(1 for e in sender_emails if e.is_read)
                avg_importance = sum(e.importance_score or 0 for e in sender_emails) / len(sender_emails)
                
                # Get most common category for this sender
                categories = [e.category for e in sender_emails if e.category]
                most_common_category = Counter(categories).most_common(1)[0][0] if categories else "unknown"
                
                # Get sentiment distribution
                sentiments = [e.sentiment for e in sender_emails if e.sentiment]
                sentiment_dist = Counter(sentiments)
                
                sender_stats[sender] = {
                    "email_count": count,
                    "open_rate": (opened_count / count) if count > 0 else 0,
                    "avg_importance": round(avg_importance, 3),
                    "primary_category": most_common_category,
                    "sentiment_distribution": dict(sentiment_dist),
                    "last_email_date": max(e.created_at for e in sender_emails).isoformat()
                }
            
            # Get top senders
            top_senders = sorted(
                sender_stats.items(), 
                key=lambda x: x[1]["email_count"], 
                reverse=True
            )[:limit]
            
            # Category distribution across all senders
            all_categories = [email.category for email in emails if email.category]
            category_counts = Counter(all_categories)
            
            return {
                "top_senders": [
                    {"sender": sender, **stats}
                    for sender, stats in
