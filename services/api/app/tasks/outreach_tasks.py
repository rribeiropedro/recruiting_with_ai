from datetime import UTC, datetime

import structlog
from supabase import create_client

from ..config import settings
from ..services.contact_finder import contact_finder
from ..services.email_drafter import email_drafter
from ..services.email_sender import email_sender
from .celery_app import app as celery_app

logger = structlog.get_logger()


def _db():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


@celery_app.task(bind=True, max_retries=1, default_retry_delay=10, queue="default")
def discover_contact_task(self, campaign_id: str):
    db = _db()

    campaign_row = (
        db.table("outreach_campaigns").select("*").eq("id", campaign_id).single().execute()
    )
    campaign = campaign_row.data

    app_row = (
        db.table("generated_applications")
        .select("*")
        .eq("id", campaign["application_id"])
        .single()
        .execute()
    )
    app = app_row.data

    job_row = (
        db.table("job_descriptions")
        .select("*")
        .eq("id", app["job_description_id"])
        .single()
        .execute()
    )
    job = job_row.data

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        contact = loop.run_until_complete(
            contact_finder.discover(
                company_name=job.get("company_name", ""),
                role_title=job.get("role_title", ""),
            )
        )
    finally:
        loop.close()

    if contact:
        db.table("outreach_campaigns").update({
            "contact_name": contact.name,
            "contact_title": contact.title,
            "contact_email": contact.email,
            "contact_linkedin": contact.linkedin,
            "email_verified": contact.verified,
            "verification_method": contact.method,
        }).eq("id", campaign_id).execute()
        logger.info("contact_discovered", campaign_id=campaign_id, method=contact.method)
    else:
        logger.info("contact_not_found", campaign_id=campaign_id)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5, queue="default")
def draft_email_task(self, campaign_id: str, tone: str = "conversational"):
    db = _db()

    campaign_row = (
        db.table("outreach_campaigns").select("*").eq("id", campaign_id).single().execute()
    )
    campaign = campaign_row.data

    app_row = (
        db.table("generated_applications")
        .select("*")
        .eq("id", campaign["application_id"])
        .single()
        .execute()
    )
    app = app_row.data

    job_row = (
        db.table("job_descriptions")
        .select("*")
        .eq("id", app["job_description_id"])
        .single()
        .execute()
    )
    job = job_row.data

    profile_row = (
        db.table("user_profiles")
        .select("*")
        .eq("user_id", campaign["user_id"])
        .single()
        .execute()
    )
    profile = profile_row.data

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        draft = loop.run_until_complete(
            email_drafter.draft(
                campaign_id=campaign_id,
                application_id=campaign["application_id"],
                contact_name=campaign.get("contact_name"),
                contact_title=campaign.get("contact_title"),
                company_name=job.get("company_name"),
                role_title=job.get("role_title"),
                industry=job.get("industry"),
                resume_summary=app.get("resume_text_summary", ""),
                user_name=profile.get("full_name", ""),
                user_id=campaign["user_id"],
                tone=tone,
            )
        )
    except Exception as exc:
        raise self.retry(exc=exc)
    finally:
        loop.close()

    db.table("outreach_campaigns").update({
        "email_subject": draft.subject,
        "email_body": draft.body,
        "company_context": draft.company_context,
    }).eq("id", campaign_id).execute()

    logger.info("email_drafted", campaign_id=campaign_id)


@celery_app.task(bind=True, max_retries=0, queue="email")
def send_email_task(self, campaign_id: str, provider: str = "gmail", attach_resume: bool = True):
    db = _db()

    campaign_row = (
        db.table("outreach_campaigns").select("*").eq("id", campaign_id).single().execute()
    )
    campaign = campaign_row.data

    if campaign["status"] in ("sent", "responded", "meeting_scheduled"):
        logger.info("send_skipped_already_sent", campaign_id=campaign_id)
        return

    if not campaign.get("contact_email") or not campaign.get("email_body"):
        db.table("outreach_campaigns").update(
            {"status": "drafted"}
        ).eq("id", campaign_id).execute()
        return

    profile_row = (
        db.table("user_profiles")
        .select("*")
        .eq("user_id", campaign["user_id"])
        .single()
        .execute()
    )
    profile = profile_row.data

    attachment = None
    if attach_resume:
        app_row = (
            db.table("generated_applications")
            .select("*")
            .eq("id", campaign["application_id"])
            .single()
            .execute()
        )
        app = app_row.data
        if app.get("pdf_storage_path"):
            from supabase import create_client as _sc
            sb = _sc(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
            pdf_bytes = sb.storage.from_("resumes").download(app["pdf_storage_path"])
            filename = (
                f"{profile.get('full_name', 'Candidate').replace(' ', '_')}_Resume.pdf"
            )
            attachment = (filename, pdf_bytes)

    import asyncio
    loop = asyncio.new_event_loop()
    try:
        if provider == "gmail":
            result = loop.run_until_complete(
                email_sender.send_gmail(
                    user_id=campaign["user_id"],
                    user_email=profile.get("email", ""),
                    gmail_oauth_token=profile.get("gmail_oauth_token"),
                    to_email=campaign["contact_email"],
                    subject=campaign["email_subject"] or "",
                    body=campaign["email_body"],
                    attachment=attachment,
                )
            )
        else:
            result = loop.run_until_complete(
                email_sender.send_outlook(
                    user_id=campaign["user_id"],
                    user_email=profile.get("email", ""),
                    outlook_oauth_token=profile.get("outlook_oauth_token"),
                    to_email=campaign["contact_email"],
                    subject=campaign["email_subject"] or "",
                    body=campaign["email_body"],
                    attachment=attachment,
                )
            )
    finally:
        loop.close()

    if result.success:
        db.table("outreach_campaigns").update({
            "status": "sent",
            "email_sent_at": datetime.now(UTC).isoformat(),
            "email_message_id": result.message_id,
            "email_thread_id": result.thread_id,
            "send_error": None,
        }).eq("id", campaign_id).execute()
        logger.info("email_sent", campaign_id=campaign_id, provider=provider)
    else:
        db.table("outreach_campaigns").update({
            "status": "drafted",
            "send_error": result.error,
        }).eq("id", campaign_id).execute()
        logger.error("email_send_failed", campaign_id=campaign_id, error=result.error)


@celery_app.task(queue="default")
def check_replies_task():
    """Periodic task — runs every 15 minutes via Celery Beat."""
    db = _db()

    campaigns_row = db.table("outreach_campaigns").select("*").eq("status", "sent").execute()
    sent_campaigns = campaigns_row.data or []

    for campaign in sent_campaigns:
        if not campaign.get("email_thread_id"):
            continue
        # Reply detection requires gmail.readonly scope (stretch goal)
        # For now, thread_id is stored and ready for when that scope is added


# Register the beat schedule on the celery app
celery_app.conf.beat_schedule = {
    "check-replies-every-15-min": {
        "task": "app.tasks.outreach_tasks.check_replies_task",
        "schedule": 900,
    },
}
