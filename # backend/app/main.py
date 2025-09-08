# backend/app/main.py
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from .core.config import settings
from .api.v1 import auth, emails, analytics, subscriptions, ai_insights
from .core.database import engine, Base
import asyncio

# Initialize Sentry for error tracking
if settings.ENVIRONMENT == "production":
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        integrations=[FastApiIntegration()],
        traces_sample_rate=0.1,
    )

# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.DEBUG else ["https://yourdomain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables on startup
@app.on_event("startup")
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Include API routers
app.include_router(auth.router, prefix=settings.API_V1_STR, tags=["authentication"])
app.include_router(emails.router, prefix=settings.API_V1_STR, tags=["emails"])
app.include_router(analytics.router, prefix=settings.API_V1_STR, tags=["analytics"])
app.include_router(subscriptions.router, prefix=settings.API_V1_STR, tags=["subscriptions"])
app.include_router(ai_insights.router, prefix=settings.API_V1_STR, tags=["ai"])

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}

@app.get("/")
async def root():
    return {"message": "EmailMind API", "version": settings.VERSION}
