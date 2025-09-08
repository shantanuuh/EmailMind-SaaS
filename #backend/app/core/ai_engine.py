#backend/app/core/ai_engine.py
import asyncio
import json
from typing import List, Dict, Any, Optional
import openai
from transformers import pipeline, AutoTokenizer, AutoModelForSequenceClassification
import numpy as np
from datetime import datetime, timedelta
import logging
from .config import settings

logger = logging.getLogger(__name__)

class AIEngine:
    def __init__(self):
        self.openai_client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.sentiment_analyzer = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest"
        )
        self.classification_model = None
        self.setup_classification_model()
    
    def setup_classification_model(self):
        """Initialize email classification model"""
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(
                "microsoft/DialoGPT-medium"
            )
            logger.info("Classification model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load classification model: {e}")
    
    async def classify_email(self, email_content: str, subject: str = "") -> Dict[str, Any]:
        """Classify email using AI"""
        try:
            prompt = f"""
            Classify this email into one of these categories:
            - work: Professional/business emails
            - personal: Personal correspondence
            - promotional: Marketing/promotional content
            - notification: System notifications/alerts
            - spam: Unwanted/spam emails
            - newsletter: Newsletters/subscriptions
            
            Email Subject: {subject}
            Email Content: {email_content[:500]}...
            
            Return only the category name and confidence score (0-1) in JSON format:
            {{"category": "category_name", "confidence": 0.95}}
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an email classification expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=100
            )
            
            result = json.loads(response.choices[0].message.content.strip())
            return result
            
        except Exception as e:
            logger.error(f"Email classification failed: {e}")
            return {"category": "unknown", "confidence": 0.0}
    
    async def analyze_sentiment(self, text: str) -> Dict[str, Any]:
        """Analyze sentiment of email content"""
        try:
            # Truncate text to avoid token limits
            text = text[:512]
            result = self.sentiment_analyzer(text)[0]
            
            # Convert to standardized format
            sentiment_mapping = {
                "LABEL_0": "negative",
                "LABEL_1": "neutral", 
                "LABEL_2": "positive"
            }
            
            return {
                "sentiment": sentiment_mapping.get(result["label"], result["label"].lower()),
                "confidence": result["score"],
                "raw_result": result
            }
            
        except Exception as e:
            logger.error(f"Sentiment analysis failed: {e}")
            return {"sentiment": "neutral", "confidence": 0.0, "raw_result": None}
    
    async def calculate_importance_score(self, email_data: Dict) -> float:
        """Calculate email importance score using AI"""
        try:
            # Extract features
            sender = email_data.get("sender", "")
            subject = email_data.get("subject", "")
            content = email_data.get("content", "")[:1000]
            has_attachments = email_data.get("has_attachments", False)
            
            prompt = f"""
            Score this email's importance from 0.0 to 1.0 based on:
            - Sender authority and relationship
            - Subject urgency and relevance
            - Content importance
            - Attachments presence
            
            Sender: {sender}
            Subject: {subject}
            Has Attachments: {has_attachments}
            Content: {content}
            
            Return only a number between 0.0 and 1.0:
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an email importance scoring expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=10
            )
            
            score = float(response.choices[0].message.content.strip())
            return max(0.0, min(1.0, score))
            
        except Exception as e:
            logger.error(f"Importance scoring failed: {e}")
            return 0.5
    
    async def generate_insights(self, emails: List[Dict], time_period: str = "week") -> Dict[str, Any]:
        """Generate AI-powered insights from email data"""
        try:
            if not emails:
                return {"insights": [], "summary": "No emails to analyze"}
            
            # Prepare email summary
            email_summary = {
                "total_emails": len(emails),
                "categories": {},
                "sentiments": {"positive": 0, "neutral": 0, "negative": 0},
                "top_senders": {},
                "time_pattern": {}
            }
            
            # Analyze patterns
            for email in emails:
                # Categories
                category = email.get("category", "unknown")
                email_summary["categories"][category] = email_summary["categories"].get(category, 0) + 1
                
                # Sentiments
                sentiment = email.get("sentiment", "neutral")
                if sentiment in email_summary["sentiments"]:
                    email_summary["sentiments"][sentiment] += 1
                
                # Senders
                sender = email.get("sender", "unknown")
                email_summary["top_senders"][sender] = email_summary["top_senders"].get(sender, 0) + 1
            
            # Generate insights using GPT
            prompt = f"""
            Analyze these email patterns and provide 3-5 actionable insights:
            
            Email Summary for {time_period}:
            - Total emails: {email_summary['total_emails']}
            - Categories: {email_summary['categories']}
            - Sentiment distribution: {email_summary['sentiments']}
            - Top senders: {dict(list(email_summary['top_senders'].items())[:5])}
            
            Provide insights in this JSON format:
            {{
                "insights": [
                    {{"type": "productivity", "title": "Insight Title", "description": "Detailed insight", "action": "Recommended action"}},
                    ...
                ],
                "summary": "Overall summary of email patterns",
                "recommendations": ["recommendation1", "recommendation2", ...]
            }}
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an email productivity and analytics expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            insights = json.loads(response.choices[0].message.content.strip())
            insights["metadata"] = email_summary
            return insights
            
        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
            return {
                "insights": [{"type": "error", "title": "Analysis Error", "description": "Unable to generate insights", "action": "Try again later"}],
                "summary": "Analysis temporarily unavailable",
                "recommendations": [],
                "metadata": {}
            }
    
    async def identify_unsubscribe_candidates(self, emails: List[Dict]) -> List[Dict]:
        """AI identifies emails that user might want to unsubscribe from"""
        try:
            newsletter_emails = [e for e in emails if e.get("category") == "newsletter" or e.get("category") == "promotional"]
            
            if not newsletter_emails:
                return []
            
            # Group by sender
            sender_stats = {}
            for email in newsletter_emails:
                sender = email.get("sender", "")
                if sender not in sender_stats:
                    sender_stats[sender] = {
                        "count": 0,
                        "opened": 0,
                        "last_opened": None,
                        "emails": []
                    }
                
                sender_stats[sender]["count"] += 1
                sender_stats[sender]["emails"].append(email)
                
                if email.get("opened", False):
                    sender_stats[sender]["opened"] += 1
                    sender_stats[sender]["last_opened"] = email.get("date")
            
            candidates = []
            for sender, stats in sender_stats.items():
                open_rate = stats["opened"] / stats["count"] if stats["count"] > 0 else 0
                
                # Identify candidates based on low engagement
                if stats["count"] > 5 and open_rate < 0.1:  # More than 5 emails, less than 10% open rate
                    candidates.append({
                        "sender": sender,
                        "email_count": stats["count"],
                        "open_rate": open_rate,
                        "recommendation_reason": f"Low engagement: {open_rate*100:.1f}% open rate over {stats['count']} emails",
                        "confidence": min(0.9, (1 - open_rate) * (stats["count"] / 20))
                    })
            
            # Sort by confidence
            candidates.sort(key=lambda x: x["confidence"], reverse=True)
            return candidates[:10]  # Return top 10 candidates
            
        except Exception as e:
            logger.error(f"Unsubscribe candidate identification failed: {e}")
            return []
    
    async def generate_executive_summary(self, user_id: int, time_period: str = "week") -> Dict[str, Any]:
        """Generate executive summary of email activity"""
        try:
            # This would typically fetch data from database
            # For now, we'll create a template structure
            
            prompt = f"""
            Create an executive summary for email activity over the past {time_period}.
            
            Structure the response as JSON with:
            {{
                "period": "{time_period}",
                "key_metrics": {{
                    "total_emails": "number",
                    "important_emails": "number", 
                    "response_rate": "percentage",
                    "avg_response_time": "hours"
                }},
                "highlights": [
                    "Key highlight 1",
                    "Key highlight 2"
                ],
                "concerns": [
                    "Concern 1",
                    "Concern 2"
                ],
                "recommendations": [
                    "Recommendation 1",
                    "Recommendation 2"
                ]
            }}
            """
            
            response = await self.openai_client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an executive email productivity advisor."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=600
            )
            
            summary = json.loads(response.choices[0].message.content.strip())
            summary["generated_at"] = datetime.utcnow().isoformat()
            return summary
            
        except Exception as e:
            logger.error(f"Executive summary generation failed: {e}")
            return {
                "period": time_period,
                "key_metrics": {},
                "highlights": [],
                "concerns": ["Unable to generate summary"],
                "recommendations": ["Try again later"],
                "generated_at": datetime.utcnow().isoformat()
            }
    
    async def predict_email_trends(self, historical_data: List[Dict]) -> Dict[str, Any]:
        """Predict future email trends based on historical data"""
        try:
            if len(historical_data) < 7:  # Need at least a week of data
                return {"prediction": "Insufficient data for trend analysis"}
            
            # Simple trend analysis (would be more sophisticated in production)
            recent_volume = len([e for e in historical_data[-7:]])  # Last 7 days
            previous_volume = len([e for e in historical_data[-14:-7]])  # Previous 7 days
            
            trend_direction = "increasing" if recent_volume > previous_volume else "decreasing"
            trend_percentage = abs((recent_volume - previous_volume) / previous_volume * 100) if previous_volume > 0 else 0
            
            return {
                "trend_direction": trend_direction,
                "trend_percentage": round(trend_percentage, 1),
                "predicted_next_week": int(recent_volume * (1 + (trend_percentage/100 if trend_direction == "increasing" else -trend_percentage/100))),
                "confidence": min(0.8, len(historical_data) / 30),  # Higher confidence with more data
                "recommendation": f"Email volume is {trend_direction} by {trend_percentage:.1f}%"
            }
            
        except Exception as e:
            logger.error(f"Trend prediction failed: {e}")
            return {"prediction": "Trend analysis temporarily unavailable"}

# Singleton instance
ai_engine = AIEngine()
