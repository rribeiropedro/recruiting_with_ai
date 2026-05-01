"use client"

import { createClient } from "@/lib/supabase/client"

export const NODE_TYPES = [
  "work",
  "research",
  "project",
  "hackathon",
  "certification",
  "education",
  "leadership",
  "volunteer",
] as const

export type NodeType = (typeof NODE_TYPES)[number]

export type NodeSource = "manual" | "bulk_import"

export interface NodePayload {
  title: string
  organization: string | null
  role: string | null
  start_date: string | null
  end_date: string | null
  description: string
  bullet_points: string[]
  node_type: NodeType
}

export type NodeUpdatePayload = Partial<NodePayload>

export interface NodeResponse extends NodePayload {
  id: string
  tags: string[]
  is_embedded: boolean
  source: NodeSource
  is_archived: boolean
  created_at: string
  updated_at: string
}

export interface NodeListResponse {
  nodes: NodeResponse[]
  total: number
  cursor: string | null
}

export interface BulkImportStatus {
  task_id: string
  status: string
  nodes_created: number
  total_nodes: number | null
  error_message: string | null
}

export interface BulkImportPreview {
  task_id: string
  nodes: NodePayload[]
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const RESUME_BUCKET = process.env.NEXT_PUBLIC_SUPABASE_RESUME_BUCKET ?? "resumes"

async function authHeader(): Promise<Record<string, string>> {
  const supabase = createClient()
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) {
    throw new Error("You must be signed in to use the Vault.")
  }
  return { Authorization: `Bearer ${data.session.access_token}` }
}

async function vaultFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(init.headers as Record<string, string> | undefined),
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers })
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const body = await response.json()
      message = body.detail ?? message
    } catch {
      // Keep the generic message.
    }
    throw new Error(message)
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export async function listNodes(params: {
  type?: string | null
  search?: string | null
  cursor?: string | null
  limit?: number
}): Promise<NodeListResponse> {
  const query = new URLSearchParams()
  if (params.type) query.set("type", params.type)
  if (params.search) query.set("search", params.search)
  if (params.cursor) query.set("cursor", params.cursor)
  query.set("limit", String(params.limit ?? 20))
  return vaultFetch<NodeListResponse>(`/vault/nodes?${query.toString()}`)
}

export async function getNode(id: string): Promise<NodeResponse> {
  return vaultFetch<NodeResponse>(`/vault/nodes/${id}`)
}

export async function createNode(payload: NodePayload): Promise<NodeResponse> {
  return vaultFetch<NodeResponse>("/vault/nodes", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function updateNode(id: string, payload: NodeUpdatePayload): Promise<NodeResponse> {
  return vaultFetch<NodeResponse>(`/vault/nodes/${id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  })
}

export async function archiveNode(id: string): Promise<void> {
  await vaultFetch<void>(`/vault/nodes/${id}`, { method: "DELETE" })
}

export async function uploadResumePdf(file: File): Promise<string> {
  const supabase = createClient()
  const { data: userData, error: userError } = await supabase.auth.getUser()
  if (userError || !userData.user) {
    throw new Error("You must be signed in to upload a resume.")
  }
  const safeName = file.name.replace(/[^a-zA-Z0-9._-]/g, "_")
  const path = `${userData.user.id}/${crypto.randomUUID()}-${safeName}`
  const { error } = await supabase.storage.from(RESUME_BUCKET).upload(path, file, {
    contentType: "application/pdf",
    upsert: false,
  })
  if (error) {
    throw new Error(error.message)
  }
  return path
}

export async function startBulkImport(storagePath: string): Promise<{ task_id: string }> {
  return vaultFetch<{ task_id: string }>("/vault/bulk-import", {
    method: "POST",
    body: JSON.stringify({ storage_path: storagePath }),
  })
}

export async function getBulkImportStatus(taskId: string): Promise<BulkImportStatus> {
  return vaultFetch<BulkImportStatus>(`/vault/bulk-import/${taskId}`)
}

export async function getBulkImportPreview(taskId: string): Promise<BulkImportPreview> {
  return vaultFetch<BulkImportPreview>(`/vault/bulk-import/${taskId}/preview`)
}

export async function commitBulkImport(
  taskId: string,
  nodes: NodePayload[]
): Promise<{ task_id: string; nodes_created: number; nodes: NodeResponse[] }> {
  return vaultFetch<{ task_id: string; nodes_created: number; nodes: NodeResponse[] }>(
    `/vault/bulk-import/${taskId}/commit`,
    {
      method: "POST",
      body: JSON.stringify({ nodes }),
    }
  )
}
