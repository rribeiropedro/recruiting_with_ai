import urllib.parse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from supabase import create_client

from ..config import settings
from ..dependencies import get_current_user
from ..schemas.outreach import (
    CampaignCreateRequest,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdateRequest,
    DraftEmailRequest,
    EmailDraftResponse,
    OAuthInitiateRequest,
    OAuthStatusResponse,
    SendEmailRequest,
    SendResultResponse,
)
from ..utils.encryption import encrypt_oauth_token

router = APIRouter()
oauth_router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

VALID_TRANSITIONS: dict[str, list[str]] = {
    "drafted": ["queued", "archived"],
    "queued": ["sent", "drafted"],
    "sent": ["responded", "meeting_scheduled", "rejected", "archived"],
    "responded": ["meeting_scheduled", "rejected", "archived"],
    "meeting_scheduled": ["rejected", "archived"],
    "rejected": ["archived"],
    "archived": ["drafted"],
}


def _db():
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)


def _row_to_response(
    row: dict, company_name: str | None = None, role_title: str | None = None
) -> CampaignResponse:
    return CampaignResponse(
        id=row["id"],
        application_id=row["application_id"],
        company_name=company_name,
        role_title=role_title,
        contact_name=row.get("contact_name"),
        contact_title=row.get("contact_title"),
        contact_email=row.get("contact_email"),
        email_verified=row.get("email_verified", False),
        email_subject=row.get("email_subject"),
        email_body=row.get("email_body"),
        status=row["status"],
        follow_up_count=row.get("follow_up_count", 0),
        notes=row.get("notes"),
        send_error=row.get("send_error"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _enrich_campaign(db, row: dict) -> CampaignResponse:
    company_name = None
    role_title = None
    try:
        app_row = (
            db.table("generated_applications")
            .select("job_description_id")
            .eq("id", row["application_id"])
            .single()
            .execute()
        )
        job_id = app_row.data.get("job_description_id")
        if job_id:
            job_row = (
                db.table("job_descriptions")
                .select("company_name, role_title")
                .eq("id", job_id)
                .single()
                .execute()
            )
            company_name = job_row.data.get("company_name")
            role_title = job_row.data.get("role_title")
    except Exception:
        pass
    return _row_to_response(row, company_name=company_name, role_title=role_title)


# ─── Campaign CRUD ────────────────────────────────────────────────────────────

@router.post("/campaigns", status_code=201)
async def create_campaign(
    body: CampaignCreateRequest,
    user_id: UUID = Depends(get_current_user),
) -> CampaignResponse:
    db = _db()

    insert_data = {
        "user_id": str(user_id),
        "application_id": str(body.application_id),
        "contact_name": body.contact_name,
        "contact_email": body.contact_email,
        "contact_title": body.contact_title,
        "contact_linkedin": body.contact_linkedin,
        "status": "drafted",
    }
    result = db.table("outreach_campaigns").insert(insert_data).execute()
    row = result.data[0]

    if body.auto_discover_contact and not body.contact_email:
        from ..tasks.outreach_tasks import discover_contact_task
        discover_contact_task.delay(row["id"])

    return _enrich_campaign(db, row)


@router.get("/campaigns")
async def list_campaigns(
    status: str | None = None,
    cursor: str | None = None,
    limit: int = 20,
    user_id: UUID = Depends(get_current_user),
) -> CampaignListResponse:
    db = _db()

    query = (
        db.table("outreach_campaigns")
        .select("*")
        .eq("user_id", str(user_id))
        .order("created_at", desc=True)
        .limit(limit)
    )
    if status:
        query = query.eq("status", status)
    if cursor:
        query = query.lt("id", cursor)

    result = query.execute()
    rows = result.data or []

    counts_result = (
        db.table("outreach_campaigns")
        .select("status")
        .eq("user_id", str(user_id))
        .execute()
    )
    counts: dict[str, int] = {}
    for r in (counts_result.data or []):
        s = r["status"]
        counts[s] = counts.get(s, 0) + 1

    campaigns = [_enrich_campaign(db, row) for row in rows]
    return CampaignListResponse(campaigns=campaigns, counts=counts)


@router.get("/campaigns/{campaign_id}")
async def get_campaign(
    campaign_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> CampaignResponse:
    db = _db()
    result = (
        db.table("outreach_campaigns")
        .select("*")
        .eq("id", str(campaign_id))
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return _enrich_campaign(db, result.data)


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: UUID,
    body: CampaignUpdateRequest,
    user_id: UUID = Depends(get_current_user),
) -> CampaignResponse:
    db = _db()

    current = (
        db.table("outreach_campaigns")
        .select("*")
        .eq("id", str(campaign_id))
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )
    if not current.data:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_data = body.model_dump(exclude_none=True)

    if "status" in update_data:
        new_status = update_data["status"]
        current_status = current.data["status"]
        allowed = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot transition from '{current_status}' to '{new_status}'",
            )

    if not update_data:
        return _enrich_campaign(db, current.data)

    result = (
        db.table("outreach_campaigns")
        .update(update_data)
        .eq("id", str(campaign_id))
        .execute()
    )
    return _enrich_campaign(db, result.data[0])


# ─── Draft email ─────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/draft")
async def draft_email(
    campaign_id: UUID,
    body: DraftEmailRequest,
    user_id: UUID = Depends(get_current_user),
) -> EmailDraftResponse:
    db = _db()

    campaign_result = (
        db.table("outreach_campaigns")
        .select("*")
        .eq("id", str(campaign_id))
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )
    if not campaign_result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = campaign_result.data

    app_result = (
        db.table("generated_applications")
        .select("*")
        .eq("id", campaign["application_id"])
        .single()
        .execute()
    )
    app = app_result.data

    job_result = (
        db.table("job_descriptions")
        .select("*")
        .eq("id", app["job_description_id"])
        .single()
        .execute()
    )
    job = job_result.data

    profile_result = (
        db.table("user_profiles")
        .select("*")
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )
    profile = profile_result.data

    from ..services.email_drafter import email_drafter
    draft = await email_drafter.draft(
        campaign_id=str(campaign_id),
        application_id=campaign["application_id"],
        contact_name=campaign.get("contact_name"),
        contact_title=campaign.get("contact_title"),
        company_name=job.get("company_name"),
        role_title=job.get("role_title"),
        industry=job.get("industry"),
        resume_summary=app.get("resume_text_summary", ""),
        user_name=profile.get("full_name", ""),
        user_id=user_id,
        tone=body.tone,
    )

    db.table("outreach_campaigns").update({
        "email_subject": draft.subject,
        "email_body": draft.body,
        "company_context": draft.company_context,
    }).eq("id", str(campaign_id)).execute()

    return EmailDraftResponse(
        campaign_id=campaign_id,
        email_subject=draft.subject,
        email_body=draft.body,
        company_context_used=draft.company_context,
        tone=body.tone,
    )


# ─── Send email ───────────────────────────────────────────────────────────────

@router.post("/campaigns/{campaign_id}/send")
@limiter.limit("5/minute")
async def send_email(
    request: Request,
    campaign_id: UUID,
    body: SendEmailRequest,
    user_id: UUID = Depends(get_current_user),
) -> SendResultResponse:
    db = _db()

    campaign_result = (
        db.table("outreach_campaigns")
        .select("*")
        .eq("id", str(campaign_id))
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )
    if not campaign_result.data:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign = campaign_result.data

    if campaign["status"] in ("sent", "responded", "meeting_scheduled"):
        raise HTTPException(status_code=409, detail="Campaign already sent")

    if not campaign.get("contact_email"):
        raise HTTPException(status_code=422, detail="No contact email set")
    if not campaign.get("email_body"):
        raise HTTPException(status_code=422, detail="No email body drafted")

    from ..tasks.outreach_tasks import send_email_task
    send_email_task.apply_async(
        args=[str(campaign_id)],
        kwargs={"provider": body.provider, "attach_resume": body.attach_resume},
        queue="email",
    )

    return SendResultResponse(success=True)


# ─── OAuth flows ──────────────────────────────────────────────────────────────

@oauth_router.post("/oauth/gmail/initiate")
async def gmail_oauth_initiate(
    body: OAuthInitiateRequest,
    user_id: UUID = Depends(get_current_user),
) -> dict:
    from google_auth_oauthlib.flow import Flow

    state_parts = [str(user_id)]
    if body.return_to:
        safe_return = body.return_to if body.return_to.startswith("/") else "/"
        state_parts.append(urllib.parse.quote(safe_return, safe="/"))

    state = ":".join(state_parts)

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uris": [f"{settings.FRONTEND_URL}/api/oauth/gmail/callback"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=["https://www.googleapis.com/auth/gmail.send"],
        redirect_uri=f"{settings.FRONTEND_URL}/api/oauth/gmail/callback",
    )
    flow.state = state
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        state=state,
        prompt="consent",
    )
    return {"auth_url": auth_url}


@oauth_router.get("/oauth/gmail/callback")
async def gmail_oauth_callback(code: str, state: str):
    from google_auth_oauthlib.flow import Flow

    parts = state.split(":", 1)
    user_id = parts[0]
    return_to = urllib.parse.unquote(parts[1]) if len(parts) > 1 else None

    if return_to and not return_to.startswith("/"):
        return_to = None

    try:
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
                    "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                    "redirect_uris": [f"{settings.FRONTEND_URL}/api/oauth/gmail/callback"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            redirect_uri=f"{settings.FRONTEND_URL}/api/oauth/gmail/callback",
            state=state,
        )
        flow.fetch_token(code=code)
        creds = flow.credentials

        token_data = {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token,
        }
        encrypted = encrypt_oauth_token(token_data)

        db = _db()
        db.table("user_profiles").update(
            {"gmail_oauth_token": encrypted}
        ).eq("user_id", user_id).execute()

        redirect_url = return_to or "/settings/connections"
        return RedirectResponse(url=f"{redirect_url}?oauth=success")
    except Exception:
        redirect_url = return_to or "/settings/connections"
        return RedirectResponse(url=f"{redirect_url}?oauth=error")


@oauth_router.post("/oauth/outlook/initiate")
async def outlook_oauth_initiate(
    body: OAuthInitiateRequest,
    user_id: UUID = Depends(get_current_user),
) -> dict:
    state_parts = [str(user_id)]
    if body.return_to:
        safe_return = body.return_to if body.return_to.startswith("/") else "/"
        state_parts.append(urllib.parse.quote(safe_return, safe="/"))

    state = ":".join(state_parts)
    ms_client_id = (
        settings.MICROSOFT_OAUTH_CLIENT_ID
        if hasattr(settings, "MICROSOFT_OAUTH_CLIENT_ID")
        else ""
    )
    params = urllib.parse.urlencode({
        "client_id": ms_client_id,
        "response_type": "code",
        "redirect_uri": f"{settings.FRONTEND_URL}/api/oauth/outlook/callback",
        "scope": "Mail.Send offline_access",
        "state": state,
    })
    auth_url = f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{params}"
    return {"auth_url": auth_url}


@oauth_router.get("/oauth/outlook/callback")
async def outlook_oauth_callback(code: str, state: str):
    import httpx

    parts = state.split(":", 1)
    user_id = parts[0]
    return_to = urllib.parse.unquote(parts[1]) if len(parts) > 1 else None
    if return_to and not return_to.startswith("/"):
        return_to = None

    client_id = (
        settings.MICROSOFT_OAUTH_CLIENT_ID
        if hasattr(settings, "MICROSOFT_OAUTH_CLIENT_ID")
        else ""
    )
    client_secret = (
        settings.MICROSOFT_OAUTH_CLIENT_SECRET
        if hasattr(settings, "MICROSOFT_OAUTH_CLIENT_SECRET")
        else ""
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": f"{settings.FRONTEND_URL}/api/oauth/outlook/callback",
                },
            )
            token_data = resp.json()

        encrypted = encrypt_oauth_token({
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
        })

        db = _db()
        db.table("user_profiles").update(
            {"outlook_oauth_token": encrypted}
        ).eq("user_id", user_id).execute()

        redirect_url = return_to or "/settings/connections"
        return RedirectResponse(url=f"{redirect_url}?oauth=success")
    except Exception:
        redirect_url = return_to or "/settings/connections"
        return RedirectResponse(url=f"{redirect_url}?oauth=error")


@oauth_router.get("/oauth/status")
async def oauth_status(user_id: UUID = Depends(get_current_user)) -> OAuthStatusResponse:
    db = _db()
    result = (
        db.table("user_profiles")
        .select("gmail_oauth_token, outlook_oauth_token")
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )
    profile = result.data or {}
    return OAuthStatusResponse(
        gmail_connected=bool(profile.get("gmail_oauth_token")),
        outlook_connected=bool(profile.get("outlook_oauth_token")),
    )
