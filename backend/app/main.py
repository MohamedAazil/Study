import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.db.supabase import SupabaseNotConfiguredError
from app.routers import auth, chat, documents, exams, notifications, reports, tasks, timetable


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler = None
    if settings.enable_scheduler:
        from app.notifications.scheduler import start_scheduler

        scheduler = start_scheduler(settings)
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    app = FastAPI(title="AI Study Assistant API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SupabaseNotConfiguredError)
    async def _supabase_not_configured(_: Request, exc: SupabaseNotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.get("/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok"}

    for module in (auth, timetable, tasks, documents, chat, exams, reports, notifications):
        app.include_router(module.router)
    return app


app = create_app()
