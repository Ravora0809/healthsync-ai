from pathlib import Path
import asyncio
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.config import settings
from app.db.session import Base,engine,SessionLocal
from app.api.v1.router import api_router
from app.models import models  # register models before create_all
from app.services.reminder_email import send_due_reminder_emails
app=FastAPI(title=settings.app_name,version="1.0.0",description="HEALTHSYNC-AI personal health records prototype")
logger = logging.getLogger(__name__)
_reminder_task = None

def _send_due_reminders_once():
    db = SessionLocal()
    try:
        return send_due_reminder_emails(db)
    finally:
        db.close()

async def _reminder_email_worker():
    while True:
        try:
            await asyncio.to_thread(_send_due_reminders_once)
        except Exception:
            logger.exception("Reminder email scheduler iteration failed")
        await asyncio.sleep(60)
app.add_middleware(CORSMiddleware,allow_origins=settings.cors_origin_list,allow_credentials=True,allow_methods=["GET","POST","PATCH","PUT","DELETE","OPTIONS"],allow_headers=["Authorization","Content-Type","Accept"])
app.include_router(api_router,prefix=settings.api_prefix)
@app.on_event("startup")
async def startup():
    global _reminder_task
    Path(settings.upload_dir).mkdir(parents=True,exist_ok=True)
    Base.metadata.create_all(bind=engine)
    _reminder_task = asyncio.create_task(_reminder_email_worker())

@app.on_event("shutdown")
async def shutdown():
    global _reminder_task
    if _reminder_task is not None:
        _reminder_task.cancel()
        try:
            await _reminder_task
        except asyncio.CancelledError:
            pass
        _reminder_task = None
@app.get("/")
def root(): return {"project":"HEALTHSYNC-AI","status":"running","docs":"/docs"}
@app.get("/api/health")
def health(): return {"status":"healthy"}
@app.get("/api/health/db")
def db_health():
    with engine.connect() as c: c.execute(text("SELECT 1"))
    return {"status":"healthy","database":"connected"}
