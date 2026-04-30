from celery import Celery

from ..config import settings

app = Celery("career_engine")

app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=settings.REDIS_URL,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=300,
    task_soft_time_limit=240,
    worker_max_tasks_per_child=50,
    broker_connection_retry_on_startup=True,
)

app.autodiscover_tasks(
    [
        "app.tasks.embed_tasks",
        "app.tasks.scrape_tasks",
        "app.tasks.generate_tasks",
        "app.tasks.outreach_tasks",
    ]
)
