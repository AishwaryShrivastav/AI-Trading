"""FastAPI main application."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
try:
    from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
    PROM_AVAILABLE = True
except Exception:
    PROM_AVAILABLE = False
from fastapi import Response, HTTPException

from .config import get_settings
from .database import init_db, engine, Base
from .routers import auth, trade_cards, positions, signals, reports, upstox_advanced, accounts, ai_trader, guardrails, options, risk, scheduler as scheduler_router, hil as hil_router
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

    # Dead-man's switch: alert if we missed heartbeats from a previous run
    try:
        from .services.market_jobs import check_missed_heartbeat
        hb = check_missed_heartbeat()
        if hb.get("stale"):
            logger.critical("[STARTUP] Dead-man's switch: %s", hb["reason"])
    except Exception as exc:  # pragma: no cover
        logger.warning("Heartbeat check on startup failed: %s", exc)

    # Start market-aware scheduler (disabled in tests via SCHEDULER_ENABLED=false)
    if settings.scheduler_enabled:
        from .services.scheduler import SchedulerService
        SchedulerService.get().start()

    yield

    # Shutdown
    logger.info("Shutting down AI Trading System...")
    if settings.scheduler_enabled:
        from .services.scheduler import SchedulerService
        SchedulerService.get().shutdown()


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
app.include_router(guardrails.router)  # Guardrails API
app.include_router(options.router)  # Options API
app.include_router(risk.router)  # Risk governor (drawdown protocol)
app.include_router(scheduler_router.router)  # Scheduler status
app.include_router(hil_router.router)       # HIL relay (SSE + approve/halt)


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
        llm_provider=settings.llm_provider,
        trading_mode=settings.trading_mode
    )


# Prometheus metrics endpoint
@app.get("/metrics")
async def metrics():
    if not PROM_AVAILABLE:
        raise HTTPException(status_code=503, detail="Prometheus client not installed")
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


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

    @app.get("/hil")
    async def serve_hil():
        """Serve the HIL (Human-in-the-Loop) relay page."""
        hil_file = frontend_path / "hil.html"
        if hil_file.exists():
            return FileResponse(hil_file)
        return {"message": "HIL page not found"}
else:
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "message": "AI Trading System API",
            "docs": "/docs",
            "health": "/health",
            "hil": "/hil",
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug
    )

