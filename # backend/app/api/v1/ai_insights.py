# backend/app/api/v1/ai_insights.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import openai
import json
import asyncio

from app.core.database import get_db
from app.core.config import get_settings
from app.api.dependencies import get_current_user, check_subscription_limit
from app.models.user import User
from app.models.email import Email
from app.schemas.ai_insights import (
    EmailInsight,
    BatchInsightRequest,
    InsightSummary,
    EmailClassificationRequest,
    SentimentAnalysisResult,
    ActionableInsight,
    TrendAnalysis
)

router = APIRouter()
settings = get_settings()

# Initialize OpenAI client
openai.api_key = settings.OPENAI_API_KEY

class AIInsightService:
    """Service class for AI-powered email insights"""
    
    @staticmethod
    async def analyze_email_content(email_content: str, email_subject: str) -> Dict[str, Any]:
        """Analyze single email content using GPT-4"""
        try:
            prompt = f"""
            Analyze the following email and provide insights in JSON format:
            
            Subject: {email_subject}
            Content: {email_content[:2000]}  # Truncate for token limits
            
            Please provide analysis in the following JSON structure:
            {{
                "category": "one of: work, personal, promotional, support, notification, urgent, newsletter",
                "priority": "one of: low, medium, high, urgent",
                "sentiment": "one of: positive, neutral, negative",
                "sentiment_score": "float between -1.0 and 1.0",
                "key_topics": ["topic1", "topic2", "topic3"],
                "requires_action": true/false,
                "action_type": "one of: reply, schedule, forward, archive, delete, follow_up, none",
                "urgency_indicators": ["indicator1", "indicator2"],
                "summary": "brief 2-sentence summary",
                "confidence_score": "float between 0.0 and 1.0"
            }}
            
            Be precise and consistent with the categories and priorities.
            """
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are an expert email analyst. Provide structured, consistent analysis in valid JSON format only."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=500,
                temperature=0.3
            )
            
            result = json.loads(response.choices[0].message.content)
            return result
            
        except Exception as e:
            # Fallback analysis if GPT-4 fails
            return {
                "category": "uncategorized",
                "priority": "medium",
                "sentiment": "neutral",
                "sentiment_score": 0.0,
                "key_topics": [],
                "requires_action": False,
                "action_type": "none",
                "urgency_indicators": [],
                "summary": "Analysis unavailable",
                "confidence_score": 0.0,
                "error": str(e)
            }
    
    @staticmethod
    async def generate_actionable_insights(emails_data: List[Dict]) -> List[Dict[str, Any]]:
        """Generate actionable insights from batch email analysis"""
        try:
            # Prepare data summary for GPT-4
            summary_prompt = f"""
            Based on email analysis data for {len(emails_data)} emails, generate actionable insights:
            
            Email Categories: {json.dumps([e.get('category', 'unknown') for e in emails_data])}
            Priorities: {json.dumps([e.get('priority', 'medium') for e in emails_data])}
            Action Required: {sum(1 for e in emails_data if e.get('requires_action', False))} emails
            
            Generate 5 actionable insights in JSON format:
            {{
                "insights": [
                    {{
                        "type": "productivity" | "priority" | "time_management" | "communication" | "organization",
                        "title": "Brief insight title",
                        "description": "Detailed description with specific recommendations",
                        "impact": "high" | "medium" | "low",
                        "action_items": ["specific action 1", "specific action 2"],
                        "metrics": {{"emails_affected": number, "time_saved_minutes": number}}
                    }}
                ]
            }}
            """
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a productivity expert analyzing email patterns to provide actionable insights."},
                    {"role": "user", "content": summary_prompt}
                ],
                max_tokens=800,
                temperature=0.4
            )
            
            result = json.loads(response.choices[0].message.content)
            return result.get("insights", [])
            
        except Exception as e:
            return [{
                "type": "error",
                "title": "Analysis Error",
                "description": f"Unable to generate insights: {str(e)}",
                "impact": "low",
                "action_items": [],
                "metrics": {"emails_affected": 0, "time_saved_minutes": 0}
            }]

ai_service = AIInsightService()

@router.post("/analyze/single", response_model=EmailInsight)
async def analyze_single_email(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Analyze a single email and return AI insights"""
    # Check subscription limits
    await check_subscription_limit(current_user, "ai_analysis", db)
    
    # Get email
    result = await db.execute(
        select(Email).where(
            and_(Email.id == email_id, Email.user_id == current_user.id)
        )
    )
    email = result.scalar_one_or_none()
    
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    
    # Perform AI analysis
    analysis = await ai_service.analyze_email_content(
        email.content or "", 
        email.subject or ""
    )
    
    # Update email with AI analysis
    email.ai_category = analysis.get("category")
    email.ai_priority = analysis.get("priority")
    email.ai_sentiment = analysis.get("sentiment")
    email.ai_sentiment_score = analysis.get("sentiment_score")
    email.ai_summary = analysis.get("summary")
    email.ai_action_required = analysis.get("requires_action", False)
    email.ai_confidence_score = analysis.get("confidence_score", 0.0)
    email.ai_analyzed_at = datetime.utcnow()
    
    await db.commit()
    
    return EmailInsight(
        email_id=email.id,
        category=analysis.get("category"),
        priority=analysis.get("priority"),
        sentiment=analysis.get("sentiment"),
        sentiment_score=analysis.get("sentiment_score", 0.0),
        key_topics=analysis.get("key_topics", []),
        requires_action=analysis.get("requires_action", False),
        suggested_action=analysis.get("action_type"),
        summary=analysis.get("summary", ""),
        confidence_score=analysis.get("confidence_score", 0.0),
        analysis_timestamp=datetime.utcnow()
    )

@router.post("/analyze/batch")
async def analyze_batch_emails(
    request: BatchInsightRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Analyze multiple emails in background"""
    # Check subscription limits
    await check_subscription_limit(current_user, "batch_analysis", db)
    
    # Validate email IDs belong to user
    result = await db.execute(
        select(Email).where(
            and_(
                Email.id.in_(request.email_ids),
                Email.user_id == current_user.id
            )
        )
    )
    emails = result.scalars().all()
    
    if len(emails) != len(request.email_ids):
        raise HTTPException(
            status_code=400, 
            detail="Some emails not found or don't belong to user"
        )
    
    # Add background task for batch analysis
    background_tasks.add_task(
        process_batch_analysis, 
        [e.id for e in emails],
        current_user.id
    )
    
    return {
        "message": "Batch analysis started",
        "email_count": len(emails),
        "estimated_completion_minutes": len(emails) * 0.5
    }

async def process_batch_analysis(email_ids: List[int], user_id: int):
    """Background task to process batch email analysis"""
    from app.core.database import get_db
    
    async with get_db() as db:
        for email_id in email_ids:
            try:
                # Get email
                result = await db.execute(
                    select(Email).where(Email.id == email_id)
                )
                email = result.scalar_one_or_none()
                
                if email and not email.ai_analyzed_at:
                    # Analyze with rate limiting
                    await asyncio.sleep(1)  # Rate limit API calls
                    analysis = await ai_service.analyze_email_content(
                        email.content or "", 
                        email.subject or ""
                    )
                    
                    # Update email
                    email.ai_category = analysis.get("category")
                    email.ai_priority = analysis.get("priority")
                    email.ai_sentiment = analysis.get("sentiment")
                    email.ai_sentiment_score = analysis.get("sentiment_score")
                    email.ai_summary = analysis.get("summary")
                    email.ai_action_required = analysis.get("requires_action", False)
                    email.ai_confidence_score = analysis.get("confidence_score", 0.0)
                    email.ai_analyzed_at = datetime.utcnow()
                    
                    await db.commit()
                    
            except Exception as e:
                print(f"Error analyzing email {email_id}: {str(e)}")
                continue

@router.get("/insights/summary", response_model=InsightSummary)
async def get_insights_summary(
    days: int = Query(7, ge=1, le=30),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-generated summary of email patterns and insights"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get analyzed emails from the period
    result = await db.execute(
        select(Email).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.ai_analyzed_at.isnot(None)
            )
        ).limit(100)  # Limit for performance
    )
    emails = result.scalars().all()
    
    if not emails:
        raise HTTPException(
            status_code=404, 
            detail="No analyzed emails found in the specified period"
        )
    
    # Prepare data for insight generation
    emails_data = []
    for email in emails:
        emails_data.append({
            "category": email.ai_category,
            "priority": email.ai_priority,
            "sentiment": email.ai_sentiment,
            "sentiment_score": email.ai_sentiment_score,
            "requires_action": email.ai_action_required,
            "sender": email.sender_email
        })
    
    # Generate actionable insights
    insights = await ai_service.generate_actionable_insights(emails_data)
    
    # Calculate summary statistics
    total_emails = len(emails)
    action_required = sum(1 for e in emails if e.ai_action_required)
    avg_sentiment = sum(e.ai_sentiment_score or 0 for e in emails) / total_emails
    
    # Category distribution
    categories = {}
    for email in emails:
        cat = email.ai_category or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    
    return InsightSummary(
        period_days=days,
        total_emails_analyzed=total_emails,
        emails_requiring_action=action_required,
        average_sentiment_score=round(avg_sentiment, 2),
        category_distribution=categories,
        actionable_insights=[
            ActionableInsight(
                type=insight["type"],
                title=insight["title"],
                description=insight["description"],
                impact_level=insight["impact"],
                action_items=insight["action_items"],
                estimated_time_saved=insight["metrics"].get("time_saved_minutes", 0)
            ) for insight in insights
        ],
        generated_at=datetime.utcnow()
    )

@router.post("/classify", response_model=Dict[str, Any])
async def classify_emails(
    request: EmailClassificationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Classify emails using custom categories"""
    # Check subscription limits
    await check_subscription_limit(current_user, "classification", db)
    
    # Get emails to classify
    result = await db.execute(
        select(Email).where(
            and_(
                Email.user_id == current_user.id,
                Email.id.in_(request.email_ids) if request.email_ids else True,
                Email.received_date >= datetime.utcnow() - timedelta(days=request.days)
            )
        ).limit(request.limit or 50)
    )
    emails = result.scalars().all()
    
    classifications = {}
    
    for email in emails:
        try:
            # Create classification prompt
            prompt = f"""
            Classify this email into one of these categories: {', '.join(request.categories)}
            
            Subject: {email.subject or 'No subject'}
            Content: {(email.content or '')[:500]}
            
            Return only the category name that best fits this email.
            """
            
            response = await openai.ChatCompletion.acreate(
                model="gpt-3.5-turbo",  # Use cheaper model for classification
                messages=[
                    {"role": "system", "content": "You are an email classifier. Return only the category name."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.1
            )
            
            classification = response.choices[0].message.content.strip()
            
            # Update email if classification is valid
            if classification in request.categories:
                email.ai_category = classification
                classifications[email.id] = classification
            
        except Exception as e:
            classifications[email.id] = f"error: {str(e)}"
    
    await db.commit()
    
    return {
        "classifications": classifications,
        "total_classified": len([c for c in classifications.values() if not c.startswith("error:")]),
        "errors": len([c for c in classifications.values() if c.startswith("error:")])
    }

@router.get("/sentiment/analysis", response_model=List[SentimentAnalysisResult])
async def get_sentiment_analysis(
    days: int = Query(30, ge=1, le=90),
    sender_filter: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get detailed sentiment analysis for emails"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Build query
    query = select(Email).where(
        and_(
            Email.user_id == current_user.id,
            Email.received_date >= start_date,
            Email.ai_sentiment.isnot(None)
        )
    )
    
    if sender_filter:
        query = query.where(Email.sender_email.ilike(f"%{sender_filter}%"))
    
    result = await db.execute(query.order_by(desc(Email.received_date)).limit(100))
    emails = result.scalars().all()
    
    sentiment_results = []
    for email in emails:
        sentiment_results.append(SentimentAnalysisResult(
            email_id=email.id,
            sender_email=email.sender_email or "",
            subject=email.subject or "",
            sentiment=email.ai_sentiment or "neutral",
            sentiment_score=email.ai_sentiment_score or 0.0,
            confidence_score=email.ai_confidence_score or 0.0,
            received_date=email.received_date,
            category=email.ai_category or "uncategorized"
        ))
    
    return sentiment_results

@router.get("/trends/analysis", response_model=TrendAnalysis)
async def get_trend_analysis(
    days: int = Query(30, ge=7, le=90),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-powered trend analysis of email patterns"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get email data for trend analysis
    result = await db.execute(
        select(
            Email.ai_category,
            Email.ai_sentiment,
            Email.ai_sentiment_score,
            Email.sender_email,
            func.date_trunc('day', Email.received_date).label('date'),
            func.count(Email.id).label('count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.ai_analyzed_at.isnot(None)
            )
        ).group_by(
            Email.ai_category,
            Email.ai_sentiment,
            Email.ai_sentiment_score,
            Email.sender_email,
            func.date_trunc('day', Email.received_date)
        )
    )
    
    trend_data = result.all()
    
    if not trend_data:
        raise HTTPException(status_code=404, detail="No analyzed emails found for trend analysis")
    
    # Prepare trend summary for GPT-4 analysis
    try:
        trend_summary = {
            "total_data_points": len(trend_data),
            "date_range_days": days,
            "categories": list(set(row.ai_category for row in trend_data if row.ai_category)),
            "sentiment_distribution": {},
            "daily_volumes": {}
        }
        
        # Calculate sentiment distribution
        sentiments = [row.ai_sentiment for row in trend_data if row.ai_sentiment]
        for sentiment in sentiments:
            trend_summary["sentiment_distribution"][sentiment] = trend_summary["sentiment_distribution"].get(sentiment, 0) + 1
        
        # Generate AI insights about trends
        prompt = f"""
        Analyze email trends and provide insights in JSON format:
        
        Data summary: {json.dumps(trend_summary)}
        
        Provide analysis in this JSON structure:
        {{
            "key_trends": ["trend description 1", "trend description 2"],
            "sentiment_trend": "improving|declining|stable",
            "volume_trend": "increasing|decreasing|stable",
            "notable_patterns": ["pattern 1", "pattern 2"],
            "recommendations": ["recommendation 1", "recommendation 2"],
            "risk_areas": ["risk 1", "risk 2"],
            "confidence_level": "high|medium|low"
        }}
        """
        
        response = await openai.ChatCompletion.acreate(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert data analyst specializing in email communication patterns."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=600,
            temperature=0.3
        )
        
        ai_analysis = json.loads(response.choices[0].message.content)
        
        return TrendAnalysis(
            analysis_period_days=days,
            key_trends=ai_analysis.get("key_trends", []),
            sentiment_trend=ai_analysis.get("sentiment_trend", "stable"),
            volume_trend=ai_analysis.get("volume_trend", "stable"),
            notable_patterns=ai_analysis.get("notable_patterns", []),
            recommendations=ai_analysis.get("recommendations", []),
            risk_areas=ai_analysis.get("risk_areas", []),
            confidence_level=ai_analysis.get("confidence_level", "medium"),
            data_points_analyzed=len(trend_data),
            generated_at=datetime.utcnow()
        )
        
    except Exception as e:
        # Fallback analysis
        return TrendAnalysis(
            analysis_period_days=days,
            key_trends=["Unable to generate detailed trend analysis"],
            sentiment_trend="unknown",
            volume_trend="unknown", 
            notable_patterns=[],
            recommendations=["Ensure sufficient analyzed email data"],
            risk_areas=[],
            confidence_level="low",
            data_points_analyzed=len(trend_data),
            generated_at=datetime.utcnow()
        )
