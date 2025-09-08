# backend/app/schemas/ai_insights.py
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class EmailInsight(BaseModel):
    email_id: int = Field(..., description="Email ID")
    category: Optional[str] = Field(None, description="AI-determined category")
    priority: Optional[str] = Field(None, description="Priority level (low/medium/high/urgent)")
    sentiment: Optional[str] = Field(None, description="Sentiment (positive/neutral/negative)")
    sentiment_score: float = Field(0.0, description="Sentiment score (-1.0 to 1.0)")
    key_topics: List[str] = Field(default_factory=list, description="Key topics identified")
    requires_action: bool = Field(False, description="Whether email requires action")
    suggested_action: Optional[str] = Field(None, description="Suggested action type")
    summary: str = Field("", description="AI-generated summary")
    confidence_score: float = Field(0.0, description="Analysis confidence (0.0 to 1.0)")
    analysis_timestamp: datetime = Field(..., description="When analysis was performed")

class BatchInsightRequest(BaseModel):
    email_ids: List[int] = Field(..., description="List of email IDs to analyze")
    priority_analysis: bool = Field(True, description="Include priority analysis")
    sentiment_analysis: bool = Field(True, description="Include sentiment analysis")
    topic_extraction: bool = Field(True, description="Extract key topics")
    action_detection: bool = Field(True, description="Detect required actions")

class ActionableInsight(BaseModel):
    type: str = Field(..., description="Type of insight (productivity/priority/time_management/etc)")
    title: str = Field(..., description="Brief insight title")
    description: str = Field(..., description="Detailed description")
    impact_level: str = Field(..., description="Impact level (high/medium/low)")
    action_items: List[str] = Field(..., description="Specific recommended actions")
    estimated_time_saved: int = Field(0, description="Estimated time saved in minutes")

class InsightSummary(BaseModel):
    period_days: int = Field(..., description="Analysis period in days")
    total_emails_analyzed: int = Field(..., description="Total emails analyzed")
    emails_requiring_action: int = Field(..., description="Emails requiring action")
    average_sentiment_score: float = Field(..., description="Average sentiment score")
    category_distribution: Dict[str, int] = Field(..., description="Email category counts")
    actionable_insights: List[ActionableInsight] = Field(..., description="Generated insights")
    generated_at: datetime = Field(..., description="When summary was generated")

class EmailClassificationRequest(BaseModel):
    email_ids: Optional[List[int]] = Field(None, description="Specific email IDs to classify")
    categories: List[str] = Field(..., description="Custom categories to classify into")
    days: int = Field(7, ge=1, le=30, description="Days of emails to classify")
    limit: Optional[int] = Field(50, ge=1, le=200, description="Maximum emails to classify")

class SentimentAnalysisResult(BaseModel):
    email_id: int = Field(..., description="Email ID")
    sender_email: str = Field(..., description="Sender email address")
    subject: str = Field(..., description="Email subject")
    sentiment: str = Field(..., description="Detected sentiment")
    sentiment_score: float = Field(..., description="Sentiment score (-1.0 to 1.0)")
    confidence_score: float = Field(..., description="Analysis confidence")
    received_date: datetime = Field(..., description="When email was received")
    category: str = Field(..., description="Email category")

class TrendAnalysis(BaseModel):
    analysis_period_days: int = Field(..., description="Period analyzed in days")
    key_trends: List[str] = Field(..., description="Key trends identified")
    sentiment_trend: str = Field(..., description="Overall sentiment trend")
    volume_trend: str = Field(..., description="Email volume trend")
    notable_patterns: List[str] = Field(..., description="Notable patterns found")
    recommendations: List[str] = Field(..., description="AI recommendations")
    risk_areas: List[str] = Field(..., description="Potential risk areas")
    confidence_level: str = Field(..., description="Analysis confidence level")
    data_points_analyzed: int = Field(..., description="Number of data points")
    generated_at: datetime = Field(..., description="Analysis generation time")

class TopicExtractionResult(BaseModel):
    email_id: int = Field(..., description="Email ID")
    topics: List[str] = Field(..., description="Extracted topics")
    topic_scores: Dict[str, float] = Field(..., description="Topic relevance scores")
    primary_topic: str = Field(..., description="Most relevant topic")
    confidence: float = Field(..., description="Extraction confidence")

class EmailSimilarityResult(BaseModel):
    email_id: int = Field(..., description="Email ID")
    similar_emails: List[int] = Field(..., description="Similar email IDs")
    similarity_scores: Dict[int, float] = Field(..., description="Similarity scores")
    common_patterns: List[str] = Field(..., description="Common patterns identified")

class SmartFilterSuggestion(BaseModel):
    filter_name: str = Field(..., description="Suggested filter name")
    filter_criteria: Dict[str, Any] = Field(..., description="Filter criteria")
    estimated_matches: int = Field(..., description="Estimated email matches")
    confidence: float = Field(..., description="Suggestion confidence")
    rationale: str = Field(..., description="Why this filter is suggested")

# Request/Response wrappers
class AIInsightRequest(BaseModel):
    analysis_types: List[str] = Field(
        ["category", "priority", "sentiment"], 
        description="Types of analysis to perform"
    )
    include_summary: bool = Field(True, description="Include AI summary")
    include_topics: bool = Field(True, description="Extract key topics")
    custom_categories: Optional[List[str]] = Field(None, description="Custom category list")

class AIInsightResponse(BaseModel):
    success: bool = True
    data: EmailInsight
    processing_time_ms: int = Field(..., description="Analysis processing time")
    tokens_used: int = Field(0, description="AI tokens consumed")
    message: Optional[str] = None

class BatchInsightResponse(BaseModel):
    success: bool = True
    job_id: str = Field(..., description="Background job ID")
    estimated_completion: datetime = Field(..., description="Estimated completion time")
    email_count: int = Field(..., description="Number of emails to analyze")
    message: Optional[str] = None

class InsightJobStatus(BaseModel):
    job_id: str = Field(..., description="Job ID")
    status: str = Field(..., description="Job status (pending/processing/completed/failed)")
    progress_percentage: int = Field(0, description="Completion percentage")
    emails_processed: int = Field(0, description="Emails processed so far")
    total_emails: int = Field(0, description="Total emails to process")
    started_at: datetime = Field(..., description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    error_message: Optional[str] = Field(None, description="Error message if failed")

class AIUsageStats(BaseModel):
    user_id: int = Field(..., description="User ID")
    period_start: datetime = Field(..., description="Statistics period start")
    period_end: datetime = Field(..., description="Statistics period end")
    total_analyses: int = Field(0, description="Total AI analyses performed")
    tokens_consumed: int = Field(0, description="Total AI tokens used")
    analysis_types: Dict[str, int] = Field(..., description="Breakdown by analysis type")
    monthly_limit: int = Field(..., description="Monthly analysis limit")
    remaining_analyses: int = Field(..., description="Remaining analyses this month")
