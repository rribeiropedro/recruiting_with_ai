from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..dependencies import get_current_user
from ..schemas.jobs import JobDescriptionResponse, JobSubmitRequest, MatchResult
from ..services import job_service

router = APIRouter()


@router.post(
    "/submit",
    response_model=JobDescriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_job(
    payload: JobSubmitRequest,
    user_id: UUID = Depends(get_current_user),
) -> JobDescriptionResponse:
    try:
        return await job_service.submit_job(user_id, payload)
    except job_service.JobDispatchError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not start job analysis",
        ) from exc


@router.get("/{job_id}", response_model=JobDescriptionResponse)
async def get_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> JobDescriptionResponse:
    job = await job_service.get_job(user_id, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.post("/{job_id}/match", response_model=MatchResult)
async def match_job(
    job_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> MatchResult:
    try:
        return await job_service.match_job(user_id, job_id)
    except job_service.JobNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found") from exc
    except job_service.JobNotReady as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job description not yet processed",
        ) from exc
