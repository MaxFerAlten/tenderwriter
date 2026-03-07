"""
TenderWriter — Celery Configuration

Async task queue using Redis as broker and result backend.
"""

from celery import Celery
from celery.schedules import crontab

from app.config import settings

celery_app = Celery(
    "tenderwriter",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,
    task_soft_time_limit=3000,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=50,
    result_expires=86400,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

celery_app.conf.beat_schedule = {
    "cleanup-old-documents": {
        "task": "app.tasks.cleanup_old_documents",
        "schedule": crontab(hour=2, minute=0),
    },
    "cleanup-expired-otp": {
        "task": "app.tasks.cleanup_expired_otp",
        "schedule": crontab(hour=3, minute=0),
    },
}
