# backend/app/api/v1/analytics.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc, and_
from typing import List, Optional
from datetime import datetime, timedelta
import json

from app.core.database import get_db
from app.api.dependencies import get_current_user, check_subscription_limit
from app.models.user import User
from app.models.email import Email, EmailAccount
from app.models.analytics import EmailAnalytics, SenderAnalytics
from app.schemas.analytics import (
    AnalyticsOverview, 
    SenderStats, 
    TimeSeriesData, 
    EmailTrends,
    CategoryBreakdown
)

router = APIRouter()

@router.get("/overview", response_model=AnalyticsOverview)
async def get_analytics_overview(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get comprehensive analytics overview for the user"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Base query for user's emails in date range
    base_query = select(Email).where(
        and_(
            Email.user_id == current_user.id,
            Email.received_date >= start_date,
            Email.received_date <= end_date
        )
    )
    
    # Total email count
    total_result = await db.execute(
        select(func.count(Email.id)).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date
            )
        )
    )
    total_emails = total_result.scalar() or 0
    
    # Unread count
    unread_result = await db.execute(
        select(func.count(Email.id)).where(
            and_(
                Email.user_id == current_user.id,
                Email.is_read == False,
                Email.received_date >= start_date
            )
        )
    )
    unread_emails = unread_result.scalar() or 0
    
    # Important emails (high priority or flagged)
    important_result = await db.execute(
        select(func.count(Email.id)).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                (Email.priority == "high") | (Email.is_flagged == True)
            )
        )
    )
    important_emails = important_result.scalar() or 0
    
    # Average response time (for emails that were responded to)
    response_time_result = await db.execute(
        select(func.avg(Email.response_time_minutes)).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.response_time_minutes.isnot(None)
            )
        )
    )
    avg_response_time = response_time_result.scalar() or 0
    
    # Top categories
    category_result = await db.execute(
        select(
            Email.ai_category,
            func.count(Email.id).label('count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.ai_category.isnot(None)
            )
        ).group_by(Email.ai_category).order_by(desc('count')).limit(5)
    )
    top_categories = [
        {"category": row.ai_category, "count": row.count}
        for row in category_result.all()
    ]
    
    return AnalyticsOverview(
        total_emails=total_emails,
        unread_emails=unread_emails,
        important_emails=important_emails,
        avg_response_time_hours=round(avg_response_time / 60, 2) if avg_response_time else 0,
        top_categories=top_categories,
        date_range_days=days
    )

@router.get("/senders", response_model=List[SenderStats])
async def get_top_senders(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get top email senders with statistics"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get sender statistics
    result = await db.execute(
        select(
            Email.sender_email,
            Email.sender_name,
            func.count(Email.id).label('total_emails'),
            func.sum(func.cast(Email.is_read == False, db.Integer)).label('unread_count'),
            func.avg(func.cast(Email.ai_sentiment_score, db.Float)).label('avg_sentiment'),
            func.max(Email.received_date).label('last_email_date'),
            func.array_agg(Email.ai_category).label('categories')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.sender_email.isnot(None)
            )
        ).group_by(
            Email.sender_email, Email.sender_name
        ).order_by(
            desc('total_emails')
        ).limit(limit)
    )
    
    senders = []
    for row in result.all():
        # Get most common category for this sender
        categories = [cat for cat in row.categories if cat is not None]
        primary_category = max(set(categories), key=categories.count) if categories else "uncategorized"
        
        senders.append(SenderStats(
            sender_email=row.sender_email,
            sender_name=row.sender_name or row.sender_email,
            total_emails=row.total_emails,
            unread_emails=row.unread_count or 0,
            avg_sentiment=round(row.avg_sentiment or 0, 2),
            last_email_date=row.last_email_date,
            primary_category=primary_category
        ))
    
    return senders

@router.get("/trends/time-series", response_model=TimeSeriesData)
async def get_email_time_series(
    days: int = Query(30, ge=1, le=365),
    granularity: str = Query("day", regex="^(hour|day|week)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get time series data for email volume and trends"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Determine date truncation based on granularity
    if granularity == "hour":
        date_trunc = func.date_trunc('hour', Email.received_date)
        format_str = "%Y-%m-%d %H:00"
    elif granularity == "week":
        date_trunc = func.date_trunc('week', Email.received_date)
        format_str = "%Y-%m-%d"
    else:  # day
        date_trunc = func.date_trunc('day', Email.received_date)
        format_str = "%Y-%m-%d"
    
    # Get email volume over time
    volume_result = await db.execute(
        select(
            date_trunc.label('period'),
            func.count(Email.id).label('email_count'),
            func.sum(func.cast(Email.is_read == False, db.Integer)).label('unread_count'),
            func.sum(func.cast(Email.priority == 'high', db.Integer)).label('high_priority_count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date
            )
        ).group_by(date_trunc).order_by(date_trunc)
    )
    
    # Format data points
    data_points = []
    for row in volume_result.all():
        data_points.append({
            "timestamp": row.period.strftime(format_str),
            "total_emails": row.email_count,
            "unread_emails": row.unread_count or 0,
            "high_priority_emails": row.high_priority_count or 0
        })
    
    # Calculate trends (percentage change from previous period)
    current_period_emails = sum(point["total_emails"] for point in data_points[-7:]) if len(data_points) >= 7 else 0
    previous_period_emails = sum(point["total_emails"] for point in data_points[-14:-7]) if len(data_points) >= 14 else 0
    
    volume_trend = 0
    if previous_period_emails > 0:
        volume_trend = ((current_period_emails - previous_period_emails) / previous_period_emails) * 100
    
    return TimeSeriesData(
        data_points=data_points,
        granularity=granularity,
        volume_trend_percentage=round(volume_trend, 2),
        total_data_points=len(data_points)
    )

@router.get("/trends/categories", response_model=List[CategoryBreakdown])
async def get_category_trends(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get email category breakdown and trends"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Get current period category counts
    current_result = await db.execute(
        select(
            Email.ai_category,
            func.count(Email.id).label('count'),
            func.avg(func.cast(Email.ai_sentiment_score, db.Float)).label('avg_sentiment'),
            func.sum(func.cast(Email.is_read == False, db.Integer)).label('unread_count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.ai_category.isnot(None)
            )
        ).group_by(Email.ai_category)
    )
    
    # Get previous period for trend calculation
    prev_start_date = start_date - timedelta(days=days)
    prev_result = await db.execute(
        select(
            Email.ai_category,
            func.count(Email.id).label('count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= prev_start_date,
                Email.received_date < start_date,
                Email.ai_category.isnot(None)
            )
        ).group_by(Email.ai_category)
    )
    
    # Create lookup for previous counts
    prev_counts = {row.ai_category: row.count for row in prev_result.all()}
    
    # Calculate trends
    categories = []
    total_emails = 0
    
    for row in current_result.all():
        current_count = row.count
        prev_count = prev_counts.get(row.ai_category, 0)
        
        # Calculate trend
        trend = 0
        if prev_count > 0:
            trend = ((current_count - prev_count) / prev_count) * 100
        
        total_emails += current_count
        
        categories.append(CategoryBreakdown(
            category=row.ai_category,
            email_count=current_count,
            percentage=0,  # Will calculate after we have total
            trend_percentage=round(trend, 2),
            avg_sentiment=round(row.avg_sentiment or 0, 2),
            unread_count=row.unread_count or 0
        ))
    
    # Calculate percentages
    for category in categories:
        if total_emails > 0:
            category.percentage = round((category.email_count / total_emails) * 100, 2)
    
    # Sort by email count descending
    categories.sort(key=lambda x: x.email_count, reverse=True)
    
    return categories

@router.get("/productivity", response_model=dict)
async def get_productivity_metrics(
    days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get productivity and response time metrics"""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Response time statistics
    response_stats = await db.execute(
        select(
            func.avg(Email.response_time_minutes).label('avg_response'),
            func.percentile_cont(0.5).within_group(Email.response_time_minutes).label('median_response'),
            func.min(Email.response_time_minutes).label('min_response'),
            func.max(Email.response_time_minutes).label('max_response'),
            func.count(Email.id).label('responded_emails')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date,
                Email.response_time_minutes.isnot(None)
            )
        )
    )
    
    stats = response_stats.first()
    
    # Email processing patterns (by hour of day)
    hourly_pattern = await db.execute(
        select(
            func.extract('hour', Email.received_date).label('hour'),
            func.count(Email.id).label('count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date
            )
        ).group_by(func.extract('hour', Email.received_date))
        .order_by('hour')
    )
    
    hourly_data = [{"hour": int(row.hour), "count": row.count} for row in hourly_pattern.all()]
    
    # Weekly pattern
    weekly_pattern = await db.execute(
        select(
            func.extract('dow', Email.received_date).label('day_of_week'),
            func.count(Email.id).label('count')
        ).where(
            and_(
                Email.user_id == current_user.id,
                Email.received_date >= start_date
            )
        ).group_by(func.extract('dow', Email.received_date))
        .order_by('day_of_week')
    )
    
    # Convert day of week numbers to names
    day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    weekly_data = [
        {"day": day_names[int(row.day_of_week)], "count": row.count} 
        for row in weekly_pattern.all()
    ]
    
    return {
        "response_times": {
            "avg_response_hours": round((stats.avg_response or 0) / 60, 2),
            "median_response_hours": round((stats.median_response or 0) / 60, 2),
            "min_response_minutes": stats.min_response or 0,
            "max_response_hours": round((stats.max_response or 0) / 60, 2),
            "total_responded_emails": stats.responded_emails or 0
        },
        "patterns": {
            "hourly_distribution": hourly_data,
            "weekly_distribution": weekly_data
        }
    }
