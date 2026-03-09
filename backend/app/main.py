from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, chat, integrations, risk, teams
from app.core.config import settings
from app.core.logging import logger, setup_logging
from app.pipelines.jira_sync import run_jira_sync_for_all_teams
from app.pipelines.slack_sync import sync_slack_all_teams
from app.services.risk_engine import run_risk_scoring_for_all_teams

scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("startup", env=settings.app_env)

    # Schedule Jira sync
    scheduler.add_job(
        run_jira_sync_for_all_teams,
        trigger=IntervalTrigger(minutes=settings.jira_sync_interval_minutes),
        id="jira_sync",
        replace_existing=True,
    )

    # Schedule risk scoring
    scheduler.add_job(
        run_risk_scoring_for_all_teams,
        trigger=IntervalTrigger(minutes=settings.jira_sync_interval_minutes),
        id="risk_scoring",
        replace_existing=True,
    )

    # Schedule Slack sync
    if settings.slack_bot_token:
        scheduler.add_job(
            sync_slack_all_teams,
            trigger=IntervalTrigger(minutes=settings.slack_sync_interval_minutes),
            id="slack_sync",
            replace_existing=True,
        )
        logger.info("slack_scheduler.enabled", interval_minutes=settings.slack_sync_interval_minutes)
    else:
        logger.info("slack_scheduler.skipped", reason="no SLACK_BOT_TOKEN")

    scheduler.start()
    logger.info("scheduler.started", jobs=len(scheduler.get_jobs()))

    yield

    scheduler.shutdown(wait=False)
    logger.info("shutdown")


app = FastAPI(
    title="Agile Intelligence Platform",
    description="AI-powered risk intelligence for agile teams",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
PREFIX = "/api/v1"
app.include_router(auth.router, prefix=PREFIX)
app.include_router(teams.router, prefix=PREFIX)
app.include_router(risk.router, prefix=PREFIX)
app.include_router(chat.router, prefix=PREFIX)
app.include_router(integrations.router, prefix=PREFIX)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/v1/scheduler/status")
async def scheduler_status():
    jobs = [
        {"id": j.id, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return {"running": scheduler.running, "jobs": jobs}
