
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from ..core.ai_engine import ai_engine
from ..models.email import Email
from ..models.user import User
from ..models.analytics import AIInsight, EmailAnalytics
from ..core.database import get_db
import logging

logger = logging.getLogger(__name__)

class AIService:
    def __init__(self):
        self.ai_engine = ai_engine
    
    async def analyze_email_batch(self, user_id: int, email_ids: List[int]) -> Dict[str, Any]:
        """Analyze a batch of emails with AI"""
        try:
            db = next(get_db())
            emails = db.query(Email).filter(
                Email.id.in_(email_ids),
                Email.user_id == user_id
            ).all()
            
            if not emails:
                return {"success": False, "error": "No emails found"}
            
            analysis_results = []
            
            for email in emails:
                try:
                    # Classify email if not already classified
                    if not email.category:
                        classification = await self.ai_engine.classify_email(
                            email.body, email.subject
                        )
                        email.category = classification.get("category")
                        email.category_confidence = classification.get("confidence")
                    
                    # Analyze sentiment if not already done
                    if not email.sentiment:
                        sentiment = await self.ai_engine.analyze_sentiment(email.body)
                        email.sentiment = sentiment.get("sentiment")
                        email.sentiment_confidence = sentiment.get("confidence")
                    
                    # Calculate importance score if not already done
                    if not email.importance_score:
                        email_data = {
                            "sender": email.sender,
                            "subject": email.subject,
                            "content": email.body,
                            "has_attachments": email.has_attachments
                        }
                        email.importance_score = await self.ai_engine.calculate_importance_score(email_data)
                    
                    analysis_results.append({
                        "email_id": email.id,
                        "category": email.category,
                        "sentiment": email.sentiment,
                        "importance_score": email.importance_score,
                        "analyzed_at": datetime.utcnow().isoformat()
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to analyze email {email.id}: {e}")
                    continue
            
            db.commit()
            
            return {
                "success": True,
                "analyzed_count": len(analysis_results),
                "results": analysis_results
            }
            
        except Exception as e:
            logger.error(f"Batch analysis failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_user_insights(self, user_id: int, time_period: str = "week") -> Dict[str, Any]:
        """Generate AI insights for user's email patterns"""
        try:
            db = next(get_db())
            
            # Calculate date range
            if time_period == "week":
                start_date = datetime.utcnow() - timedelta(weeks=1)
            elif time_period == "month":
                start_date = datetime.utcnow() - timedelta(days=30)
            elif time_period == "quarter":
                start_date = datetime.utcnow() - timedelta(days=90)
            else:
                start_date = datetime.utcnow() - timedelta(weeks=1)
            
            # Fetch user emails
            emails = db.query(Email).filter(
                Email.user_id == user_id,
                Email.created_at >= start_date
            ).all()
            
            if not emails:
                return {"success": False, "error": "No emails found for analysis"}
            
            # Convert to dict format for AI analysis
            email_data = []
            for email in emails:
                email_data.append({
                    "id": email.id,
                    "sender": email.sender,
                    "subject": email.subject,
                    "category": email.category,
                    "sentiment": email.sentiment,
                    "importance_score": email.importance_score,
                    "date": email.created_at.isoformat() if email.created_at else None,
                    "opened": email.is_read
                })
            
            # Generate insights using AI engine
            insights = await self.ai_engine.generate_insights(email_data, time_period)
            
            # Store insights in database
            ai_insight = AIInsight(
                user_id=user_id,
                insight_type="email_patterns",
                time_period=time_period,
                insights_data=insights,
                generated_at=datetime.utcnow()
            )
            
            db.add(ai_insight)
            db.commit()
            
            return {
                "success": True,
                "insights": insights,
                "insight_id": ai_insight.id,
                "generated_at": ai_insight.generated_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_unsubscribe_recommendations(self, user_id: int) -> Dict[str, Any]:
        """Get AI-powered unsubscribe recommendations"""
        try:
            db = next(get_db())
            
            # Get last 3 months of newsletter/promotional emails
            start_date = datetime.utcnow() - timedelta(days=90)
            emails = db.query(Email).filter(
                Email.user_id == user_id,
                Email.created_at >= start_date,
                Email.category.in_(["newsletter", "promotional"])
            ).all()
            
            if not emails:
                return {"success": False, "error": "No newsletter/promotional emails found"}
            
            # Convert to dict format
            email_data = []
            for email in emails:
                email_data.append({
                    "sender": email.sender,
                    "category": email.category,
                    "opened": email.is_read,
                    "date": email.created_at.isoformat() if email.created_at else None
                })
            
            # Get recommendations from AI engine
            candidates = await self.ai_engine.identify_unsubscribe_candidates(email_data)
            
            return {
                "success": True,
                "recommendations": candidates,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Unsubscribe recommendations failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def generate_executive_summary(self, user_id: int, time_period: str = "week") -> Dict[str, Any]:
        """Generate executive summary for user"""
        try:
            db = next(get_db())
            
            # Check user subscription level
            user = db.query(User).filter(User.id == user_id).first()
            if not user or user.subscription_tier not in ["professional", "enterprise"]:
                return {"success": False, "error": "Executive summary requires Professional or Enterprise plan"}
            
            summary = await self.ai_engine.generate_executive_summary(user_id, time_period)
            
            # Store summary
            ai_insight = AIInsight(
                user_id=user_id,
                insight_type="executive_summary",
                time_period=time_period,
                insights_data=summary,
                generated_at=datetime.utcnow()
            )
            
            db.add(ai_insight)
            db.commit()
            
            return {
                "success": True,
                "summary": summary,
                "insight_id": ai_insight.id
            }
            
        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def predict_email_trends(self, user_id: int) -> Dict[str, Any]:
        """Predict future email trends for user"""
        try:
            db = next(get_db())
            
            # Get historical data (last 30 days)
            start_date = datetime.utcnow() - timedelta(days=30)
            emails = db.query(Email).filter(
                Email.user_id == user_id,
                Email.created_at >= start_date
            ).order_by(Email.created_at).all()
            
            if len(emails) < 7:
                return {"success": False, "error": "Insufficient data for trend prediction"}
            
            # Convert to dict format with daily aggregation
            daily_counts = {}
            for email in emails:
                date_key = email.created_at.date().isoformat()
                daily_counts[date_key] = daily_counts.get(date_key, 0) + 1
            
            historical_data = [{"date": date, "count": count} for date, count in daily_counts.items()]
            
            predictions = await self.ai_engine.predict_email_trends(historical_data)
            
            return {
                "success": True,
                "predictions": predictions,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Trend prediction failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_ai_insights_history(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get user's AI insights history"""
        try:
            db = next(get_db())
            
            insights = db.query(AIInsight).filter(
                AIInsight.user_id == user_id
            ).order_by(AIInsight.generated_at.desc()).limit(limit).all()
            
            return [
                {
                    "id": insight.id,
                    "type": insight.insight_type,
                    "time_period": insight.time_period,
                    "data": insight.insights_data,
                    "generated_at": insight.generated_at.isoformat()
                }
                for insight in insights
            ]
            
        except Exception as e:
            logger.error(f"Insights history retrieval failed: {e}")
            return []
    
    async def smart_email_summary(self, email_id: int, user_id: int) -> Dict[str, Any]:
        """Generate AI summary for a specific email"""
        try:
            db = next(get_db())
            
            email = db.query(Email).filter(
                Email.id == email_id,
                Email.user_id == user_id
            ).first()
            
            if not email:
                return {"success": False, "error": "Email not found"}
            
            # Use AI to summarize email content
            prompt = f"""
            Summarize this email in 2-3 sentences, highlighting key points and any required actions:
            
            Subject: {email.subject}
            From: {email.sender}
            Content: {email.body[:1000]}...
            
            Format as JSON:
            {{
                "summary": "Brief summary",
                "key_points": ["point1", "point2", "point3"],
                "action_required": true/false,
                "urgency": "low/medium/high"
            }}
            """
            
            # This would call the AI engine - simplified for demo
            summary = {
                "summary": "AI-generated email summary would appear here",
                "key_points": ["Key point 1", "Key point 2"],
                "action_required": False,
                "urgency": "low"
            }
            
            return {
                "success": True,
                "email_id": email_id,
                "summary": summary,
                "generated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Email summary generation failed: {e}")
            return {"success": False, "error": str(e)}

# Singleton instance
ai_service = AIService()
