"""FastAPI main application."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from .config import get_settings
from .database import init_db, engine, Base
from .routers import auth, trade_cards, positions, signals, reports, upstox_advanced, accounts, ai_trader
from .schemas import HealthResponse
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting AI Trading System...")
    
    # Initialize database
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized")
    
    # TODO: Initialize scheduler for daily jobs
    # scheduler = AsyncIOScheduler()
    # scheduler.start()
    
    yield
    
    # Shutdown
    logger.info("Shutting down AI Trading System...")


# Create FastAPI app
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Semi-automated Indian equities trading with AI signals and manual approval",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(trade_cards.router)
app.include_router(positions.router)
app.include_router(signals.router)
app.include_router(reports.router)
app.include_router(upstox_advanced.router)
app.include_router(accounts.router)  # Multi-account AI Trader
app.include_router(ai_trader.router)  # AI Trader Pipeline


# Health check
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version="1.0.0",
        database="sqlite",
        broker="upstox",
        llm_provider=settings.llm_provider
    )


# Mount static files and serve frontend
frontend_path = Path(__file__).parent.parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_path / "static")), name="static")
    
    @app.get("/")
    async def serve_frontend():
        """Serve frontend HTML."""
        index_file = frontend_path / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"message": "Frontend not found. Please create frontend/index.html"}
else:
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "AI Trading System API",
            "docs": "/docs",
            "health": "/health"
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )

