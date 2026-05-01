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
