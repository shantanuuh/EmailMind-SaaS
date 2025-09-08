# backend/app/schemas/analytics.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class CategoryCount(BaseModel):
    category: str
    count: int

class AnalyticsOverview(BaseModel):
    total_emails: int = Field(..., description="Total emails in date range")
    unread_emails: int = Field(..., description="Number of unread emails")
    important_emails: int = Field(..., description="Number of important/high priority emails")
    avg_response_time_hours: float = Field(..., description="Average response time in hours")
    top_categories: List[CategoryCount] = Field(..., description="Top email categories")
    date_range_days: int = Field(..., description="Number of days analyzed")

class SenderStats(BaseModel):
    sender_email: str = Field(..., description="Sender's email address")
    sender_name: str = Field(..., description="Sender's display name")
    total_emails: int = Field(..., description="Total emails from this sender")
    unread_emails: int = Field(..., description="Unread emails from this sender")
    avg_sentiment: float = Field(..., description="Average sentiment score (-1 to 1)")
    last_email_date: datetime = Field(..., description="Date of most recent email")
    primary_category: str = Field(..., description="Most common email category from this sender")

class TimeSeriesDataPoint(BaseModel):
    timestamp: str = Field(..., description="Time period (formatted)")
    total_emails: int = Field(..., description="Total emails in this period")
    unread_emails: int = Field(..., description="Unread emails in this period")
    high_priority_emails: int = Field(..., description="High priority emails in this period")

class TimeSeriesData(BaseModel):
    data_points: List[TimeSeriesDataPoint] = Field(..., description="Time series data points")
    granularity: str = Field(..., description="Time granularity (hour/day/week)")
    volume_trend_percentage: float = Field(..., description="Volume trend compared to previous period")
    total_data_points: int = Field(..., description="Total number of data points")

class CategoryBreakdown(BaseModel):
    category: str = Field(..., description="Email category name")
    email_count: int = Field(..., description="Number of emails in this category")
    percentage: float = Field(..., description="Percentage of total emails")
    trend_percentage: float = Field(..., description="Trend compared to previous period")
    avg_sentiment: float = Field(..., description="Average sentiment for this category")
    unread_count: int = Field(..., description="Unread emails in this category")

class EmailTrends(BaseModel):
    daily_volume: List[Dict[str, Any]] = Field(..., description="Daily email volume data")
    weekly_patterns: Dict[str, int] = Field(..., description="Weekly email patterns")
    hourly_patterns: Dict[str, int] = Field(..., description="Hourly email patterns")
    sentiment_trends: List[Dict[str, Any]] = Field(..., description="Sentiment over time")

class ProductivityMetrics(BaseModel):
    avg_response_time_hours: float = Field(..., description="Average response time in hours")
    emails_responded_to: int = Field(..., description="Number of emails responded to")
    response_rate: float = Field(..., description="Response rate percentage")
    peak_activity_hours: List[int] = Field(..., description="Hours with highest email activity")
    busiest_days: List[str] = Field(..., description="Days with most email activity")

# Request schemas
class AnalyticsRequest(BaseModel):
    days: int = Field(30, ge=1, le=365, description="Number of days to analyze")
    include_categories: Optional[List[str]] = Field(None, description="Filter by categories")
    sender_filter: Optional[str] = Field(None, description="Filter by sender email/domain")

class SenderStatsRequest(BaseModel):
    limit: int = Field(20, ge=1, le=100, description="Maximum number of senders to return")
    days: int = Field(30, ge=1, le=365, description="Number of days to analyze")
    min_emails: int = Field(1, ge=1, description="Minimum emails from sender to include")

class TimeSeriesRequest(BaseModel):
    days: int = Field(30, ge=1, le=365, description="Number of days to analyze")
    granularity: str = Field("day", regex="^(hour|day|week)$", description="Time granularity")
    metrics: List[str] = Field(["volume"], description="Metrics to include")

# Response wrappers
class AnalyticsResponse(BaseModel):
    success: bool = True
    data: AnalyticsOverview
    message: Optional[str] = None

class SenderStatsResponse(BaseModel):
    success: bool = True
    data: List[SenderStats]
    total_senders: int
    message: Optional[str] = None

class TimeSeriesResponse(BaseModel):
    success: bool = True
    data: TimeSeriesData
    message: Optional[str] = None
