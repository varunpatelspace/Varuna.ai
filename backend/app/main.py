"""
VARUNA AI - Production Backend Application Entrypoint.
Hexagonal architecture with FastAPI, SQLAlchemy, and clean service layers.
"""

import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine, Base, SessionLocal
from app.api import auth, chat, billing, files, admin
from app.services.payment_service import PaymentService
from app.services.ai_gateway import AIGateway
from app.models.user import User
from app.utils.security import hash_password

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("varuna.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle management."""
    logger.info("Initializing database schema and seed data...")
    Base.metadata.create_all(bind=engine)

    # Seed baseline configurations
    with SessionLocal() as db:
        PaymentService.seed_plans(db)
        AIGateway.seed_default_models(db)

        # Seed initial platform administrator if not present
        admin_user = db.query(User).filter(User.email == "admin@varuna.ai").first()
        if not admin_user:
            admin_user = User(
                email="admin@varuna.ai",
                hashed_password=hash_password("AdminPass123!"),
                full_name="Varuna Platform Administrator",
                is_active=True,
                is_verified=True,
                is_platform_admin=True
            )
            db.add(admin_user)
            db.commit()
            logger.info("Default platform administrator created: admin@varuna.ai")

    logger.info("VARUNA AI backend started successfully.")
    yield
    logger.info("VARUNA AI backend shutting down.")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Production-Grade Multi-Tenant AI Assistant Platform",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_correlation_and_error_handling(request: Request, call_next):
    """
    Assigns X-Request-ID to all incoming requests and ensures unhandled
    internal exceptions never leak stack traces to clients.
    """
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        logger.error(f"Unhandled Exception [RequestID: {request_id}]: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected server error occurred. Please contact support with the request ID.",
                "request_id": request_id
            },
            headers={"X-Request-ID": request_id}
        )


# Include API Routers
app.include_router(auth.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(billing.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(admin.router, prefix="/api")


@app.get("/health")
@app.get("/api/health")
def health_check():
    """Liveness and readiness health check probe."""
    return {
        "status": "HEALTHY",
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "kill_switch_active": settings.GLOBAL_AI_KILL_SWITCH
    }
