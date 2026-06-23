import os
from celery import Celery

redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "framey_tasks",
    broker=redis_url,
    backend=redis_url,
    include=["workers.video_pipeline"]
)

celery_app.conf.update(
    task_track_started=True,
    timezone="UTC",
)
