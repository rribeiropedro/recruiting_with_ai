from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..dependencies import get_current_user
from ..schemas.vault import (
    BulkImportCommitRequest,
    BulkImportCommitResponse,
    BulkImportPreviewResponse,
    BulkImportProposedNode,
    BulkImportRequest,
    BulkImportStartResponse,
    BulkImportStatusResponse,
    NodeCreateRequest,
    NodeListResponse,
    NodeResponse,
    NodeType,
    NodeUpdateRequest,
)
from ..services import vault_service
from ..services.bulk_import_store import get_import_preview, get_import_status, set_import_status
from ..tasks.embed_tasks import dispatch_node_processing
from ..tasks.scrape_tasks import bulk_import_task

router = APIRouter()


@router.post("/nodes", response_model=NodeResponse, status_code=status.HTTP_201_CREATED)
async def create_node(
    payload: NodeCreateRequest,
    user_id: UUID = Depends(get_current_user),
) -> NodeResponse:
    node = await vault_service.create_node(user_id, payload)
    dispatch_node_processing(str(node.id))
    return node


@router.get("/nodes", response_model=NodeListResponse)
async def list_nodes(
    node_type: NodeType | None = Query(None, alias="type"),
    search: str | None = Query(None, min_length=1, max_length=200),
    cursor: UUID | None = None,
    limit: int = Query(20, ge=1, le=50),
    user_id: UUID = Depends(get_current_user),
) -> NodeListResponse:
    return await vault_service.list_nodes(
        user_id,
        node_type=node_type,
        search=search,
        cursor=cursor,
        limit=limit,
    )


@router.get("/nodes/{node_id}", response_model=NodeResponse)
async def get_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> NodeResponse:
    node = await vault_service.get_node(user_id, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


@router.put("/nodes/{node_id}", response_model=NodeResponse)
async def update_node(
    node_id: UUID,
    payload: NodeUpdateRequest,
    user_id: UUID = Depends(get_current_user),
) -> NodeResponse:
    result = await vault_service.update_node(user_id, node_id, payload)
    if not result:
        raise HTTPException(status_code=404, detail="Node not found")
    if result.reprocess:
        dispatch_node_processing(str(result.node.id))
    return result.node


@router.delete("/nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
) -> Response:
    archived = await vault_service.archive_node(user_id, node_id)
    if not archived:
        raise HTTPException(status_code=404, detail="Node not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/bulk-import",
    response_model=BulkImportStartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_bulk_import(
    payload: BulkImportRequest,
    user_id: UUID = Depends(get_current_user),
) -> BulkImportStartResponse:
    task_id = str(uuid4())
    set_import_status(
        task_id,
        status="pending",
        user_id=str(user_id),
        storage_path=payload.storage_path,
    )
    try:
        bulk_import_task.apply_async(
            args=[str(user_id), payload.storage_path],
            task_id=task_id,
            queue="heavy",
        )
    except Exception as exc:
        set_import_status(
            task_id,
            status="failed",
            user_id=str(user_id),
            storage_path=payload.storage_path,
            error_message="Could not start bulk import.",
        )
        raise HTTPException(status_code=503, detail="Could not start bulk import") from exc
    return BulkImportStartResponse(task_id=task_id)


@router.get("/bulk-import/{task_id}", response_model=BulkImportStatusResponse)
async def get_bulk_import_status(
    task_id: str,
    user_id: UUID = Depends(get_current_user),
) -> BulkImportStatusResponse:
    status_payload = get_import_status(task_id)
    if not status_payload or status_payload.get("user_id") != str(user_id):
        raise HTTPException(status_code=404, detail="Bulk import task not found")
    return BulkImportStatusResponse.model_validate(status_payload)


@router.get("/bulk-import/{task_id}/preview", response_model=BulkImportPreviewResponse)
async def get_bulk_import_preview(
    task_id: str,
    user_id: UUID = Depends(get_current_user),
) -> BulkImportPreviewResponse:
    preview = get_import_preview(task_id)
    if not preview or preview.get("user_id") != str(user_id):
        raise HTTPException(status_code=404, detail="Bulk import preview not found")
    nodes = [BulkImportProposedNode.model_validate(node) for node in preview.get("nodes", [])]
    return BulkImportPreviewResponse(task_id=task_id, nodes=nodes)


@router.post("/bulk-import/{task_id}/commit", response_model=BulkImportCommitResponse)
async def commit_bulk_import(
    task_id: str,
    payload: BulkImportCommitRequest,
    user_id: UUID = Depends(get_current_user),
) -> BulkImportCommitResponse:
    preview = get_import_preview(task_id)
    if not preview or preview.get("user_id") != str(user_id):
        raise HTTPException(status_code=404, detail="Bulk import preview not found")

    storage_path = preview["storage_path"]
    set_import_status(
        task_id,
        status="committing",
        user_id=str(user_id),
        storage_path=storage_path,
        total_nodes=len(payload.nodes),
    )

    created_nodes: list[NodeResponse] = []
    for node_payload in payload.nodes:
        dedupe_key = vault_service.build_bulk_import_dedupe_key(storage_path, node_payload)
        try:
            node = await vault_service.create_node(
                user_id,
                node_payload,
                source="bulk_import",
                metadata={
                    "storage_path": storage_path,
                    "bulk_import_task_id": task_id,
                    "dedupe_key": dedupe_key,
                },
            )
        except vault_service.DuplicateBulkImportNode:
            continue

        created_nodes.append(node)
        dispatch_node_processing(str(node.id))

    set_import_status(
        task_id,
        status="completed",
        user_id=str(user_id),
        storage_path=storage_path,
        nodes_created=len(created_nodes),
        total_nodes=len(payload.nodes),
    )
    return BulkImportCommitResponse(
        task_id=task_id,
        nodes_created=len(created_nodes),
        nodes=created_nodes,
    )
