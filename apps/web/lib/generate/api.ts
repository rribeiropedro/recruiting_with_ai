"use client"

import { createClient } from "@/lib/supabase/client"

export interface JobRequirements {
  company_name: string | null
  role_title: string | null
  technical_skills: string[]
  soft_skills: string[]
  responsibilities: string[]
  experience_years: number | null
  education: string | null
  nice_to_haves: string[]
  industry: string | null
}

export interface JobDescriptionResponse {
  id: string
  url: string | null
  company_name: string | null
  role_title: string | null
  requirements: JobRequirements
  is_embedded: boolean
  created_at: string
  status?: string | null
  error_message?: string | null
}

export interface JobSubmitPayload {
  url?: string
  raw_text?: string
}

export interface ExperienceNodeResult {
  id: string
  title: string
  organization: string | null
  role: string | null
  start_date: string | null
  end_date: string | null
  description: string
  bullet_points: string[]
  node_type: string
  tags: string[]
  similarity_score: number
}

export interface MatchResult {
  job_description_id: string
  job_requirements: JobRequirements
  matched_nodes: ExperienceNodeResult[]
  low_relevance_warning: boolean
}

export type ResumeTemplate = "modern" | "classic" | "minimal"

export type ApplicationStatus =
  | "pending"
  | "scraping"
  | "extracting"
  | "matching"
  | "rewriting"
  | "rendering"
  | "completed"
  | "failed"
  | "cache_hit"

export interface ApplicationStatusResponse {
  id: string
  status: ApplicationStatus | string
  error_message: string | null
  cache_hit: boolean
  company_name: string | null
  role_title: string | null
  matched_node_count: number
  pdf_url: string | null
  created_at: string
  completed_at: string | null
}

export interface MatchedApplicationNode {
  id?: string
  node_id?: string
  title?: string
  organization?: string | null
  role?: string | null
  description?: string
  bullet_points?: string[]
  rewritten_bullets?: string[]
  tags?: string[]
  [key: string]: unknown
}

export interface ApplicationDetailResponse extends ApplicationStatusResponse {
  matched_nodes: MatchedApplicationNode[]
  similarity_scores: number[]
  job_requirements: Record<string, unknown>
}

export interface GenerateApplicationResponse {
  application_id: string
  task_id: string
}

export interface ApplicationListResponse {
  applications: ApplicationStatusResponse[]
  cursor: string | null
}

export interface PipelineStatusResponse {
  vault_node_count: number
  last_application: {
    company_name: string | null
    created_at: string
  } | null
  outreach_counts: {
    sent: number
    responded: number
  }
}

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function authHeader(): Promise<Record<string, string>> {
  const supabase = createClient()
  const { data, error } = await supabase.auth.getSession()
  if (error || !data.session) {
    throw new Error("You must be signed in to analyze a job.")
  }
  return { Authorization: `Bearer ${data.session.access_token}` }
}

function detailToMessage(detail: unknown, fallback: string) {
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: unknown }).msg)
        }
        return null
      })
      .filter(Boolean)
      .join(" ")
  }
  return fallback
}

async function jobsFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(await authHeader()),
    ...(init.headers as Record<string, string> | undefined),
  }
  const response = await fetch(`${API_URL}${path}`, { ...init, headers })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const body = (await response.json()) as { detail?: unknown; error?: unknown }
      message = detailToMessage(body.detail ?? body.error, message)
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

export function submitJob(payload: JobSubmitPayload): Promise<JobDescriptionResponse> {
  return jobsFetch<JobDescriptionResponse>("/jobs/submit", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function getJob(id: string): Promise<JobDescriptionResponse> {
  return jobsFetch<JobDescriptionResponse>(`/jobs/${id}`)
}

export function matchJob(id: string): Promise<MatchResult> {
  return jobsFetch<MatchResult>(`/jobs/${id}/match`, { method: "POST" })
}

async function appFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init.headers as Record<string, string> | undefined),
    },
  })

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`
    try {
      const text = await response.text()
      if (text) message = text
      try {
        const body = JSON.parse(text) as { detail?: unknown; error?: unknown }
        message = detailToMessage(body.detail ?? body.error, message)
      } catch {
        // Plain text error body.
      }
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

export function generateApplication(payload: {
  job_description_id: string
  template?: ResumeTemplate
}): Promise<GenerateApplicationResponse> {
  return appFetch<GenerateApplicationResponse>("/generate/application", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function generateFromUrl(payload: {
  url?: string | null
  raw_text?: string | null
  template?: ResumeTemplate
}): Promise<GenerateApplicationResponse> {
  return appFetch<GenerateApplicationResponse>("/generate/from-url", {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export function getApplicationStatus(id: string): Promise<ApplicationStatusResponse> {
  return appFetch<ApplicationStatusResponse>(`/generate/application/${id}`)
}

export function getApplicationDetails(id: string): Promise<ApplicationDetailResponse> {
  return appFetch<ApplicationDetailResponse>(`/generate/application/${id}/details`)
}

export function getApplicationPdf(id: string): Promise<{ url: string }> {
  return appFetch<{ url: string }>(`/generate/application/${id}/pdf`)
}

export function listApplications(params: {
  cursor?: string | null
  limit?: number
} = {}): Promise<ApplicationListResponse> {
  const query = new URLSearchParams()
  if (params.cursor) query.set("cursor", params.cursor)
  query.set("limit", String(params.limit ?? 10))
  return appFetch<ApplicationListResponse>(`/generate/applications?${query.toString()}`)
}

export function regenerateApplication(id: string): Promise<GenerateApplicationResponse> {
  return appFetch<GenerateApplicationResponse>(`/generate/application/${id}/regenerate`, {
    method: "POST",
  })
}

export function getPipelineStatus(): Promise<PipelineStatusResponse> {
  return appFetch<PipelineStatusResponse>("/user/pipeline-status")
}
