"use client"

import { create } from "zustand"

export interface CampaignResponse {
  id: string
  application_id: string
  company_name: string | null
  role_title: string | null
  contact_name: string | null
  contact_title: string | null
  contact_email: string | null
  email_verified: boolean
  email_subject: string | null
  email_body: string | null
  status: CampaignStatus
  follow_up_count: number
  notes: string | null
  send_error: string | null
  created_at: string
  updated_at: string
}

export type CampaignStatus =
  | "drafted"
  | "queued"
  | "sent"
  | "opened"
  | "responded"
  | "meeting_scheduled"
  | "rejected"
  | "archived"

export interface EmailDraftResponse {
  campaign_id: string
  email_subject: string
  email_body: string
  company_context_used: Record<string, unknown>
  tone: string
}

export interface SendResultResponse {
  success: boolean
  email_message_id: string | null
  error: string | null
}

export interface RealtimeCampaignPayload {
  eventType: string
  new: Partial<CampaignResponse> | null
  old: Partial<CampaignResponse> | null
}

interface OutreachStore {
  campaigns: CampaignResponse[]
  counts: Record<string, number>
  isLoading: boolean
  error: string | null

  fetchCampaigns: (status?: string) => Promise<void>
  updateStatus: (id: string, status: CampaignStatus) => Promise<void>
  updateCampaign: (id: string, data: Partial<CampaignResponse>) => Promise<void>
  draftEmail: (id: string, tone?: string) => Promise<EmailDraftResponse>
  sendEmail: (id: string, provider?: string) => Promise<SendResultResponse>
  handleRealtimeUpdate: (payload: RealtimeCampaignPayload) => void
}

const API_BASE = "/api"

function hasCampaignId(
  campaign: Partial<CampaignResponse> | null | undefined
): campaign is CampaignResponse {
  return typeof campaign?.id === "string"
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || res.statusText)
  }
  return res.json()
}

export const useOutreachStore = create<OutreachStore>((set, get) => ({
  campaigns: [],
  counts: {},
  isLoading: false,
  error: null,

  fetchCampaigns: async (status) => {
    set({ isLoading: true, error: null })
    try {
      const params = status ? `?status=${status}` : ""
      const data = await apiFetch<{ campaigns: CampaignResponse[]; counts: Record<string, number> }>(
        `/outreach/campaigns${params}`
      )
      set({ campaigns: data.campaigns, counts: data.counts, isLoading: false })
    } catch (e) {
      set({ error: String(e), isLoading: false })
    }
  },

  updateStatus: async (id, status) => {
    const prev = get().campaigns
    set((s) => ({
      campaigns: s.campaigns.map((c) => (c.id === id ? { ...c, status } : c)),
    }))
    try {
      await apiFetch(`/outreach/campaigns/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      })
    } catch {
      set({ campaigns: prev })
    }
  },

  updateCampaign: async (id, data) => {
    await apiFetch(`/outreach/campaigns/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    })
    set((s) => ({
      campaigns: s.campaigns.map((c) => (c.id === id ? { ...c, ...data } : c)),
    }))
  },

  draftEmail: async (id, tone = "conversational") => {
    return apiFetch<EmailDraftResponse>(`/outreach/campaigns/${id}/draft`, {
      method: "POST",
      body: JSON.stringify({ tone }),
    })
  },

  sendEmail: async (id, provider = "gmail") => {
    return apiFetch<SendResultResponse>(`/outreach/campaigns/${id}/send`, {
      method: "POST",
      body: JSON.stringify({ provider, attach_resume: true }),
    })
  },

  handleRealtimeUpdate: ({ eventType, new: updated, old }) => {
    if (eventType === "INSERT" && hasCampaignId(updated)) {
      set((s) => ({ campaigns: [updated, ...s.campaigns] }))
    } else if (eventType === "UPDATE" && hasCampaignId(updated)) {
      set((s) => ({
        campaigns: s.campaigns.map((c) => (c.id === updated.id ? updated : c)),
      }))
    } else if (eventType === "DELETE" && old?.id) {
      set((s) => ({ campaigns: s.campaigns.filter((c) => c.id !== old.id) }))
    }
  },
}))

export const VALID_TRANSITIONS: Record<CampaignStatus, CampaignStatus[]> = {
  drafted: ["queued", "archived"],
  queued: ["sent", "drafted"],
  sent: ["responded", "meeting_scheduled", "rejected", "archived"],
  responded: ["meeting_scheduled", "rejected", "archived"],
  meeting_scheduled: ["rejected", "archived"],
  rejected: ["archived"],
  archived: ["drafted"],
  opened: ["responded", "meeting_scheduled", "rejected", "archived"],
}

export const STATUS_LABELS: Record<CampaignStatus, string> = {
  drafted: "Drafted",
  queued: "Queued",
  sent: "Sent",
  opened: "Opened",
  responded: "Responded",
  meeting_scheduled: "Scheduled",
  rejected: "Rejected",
  archived: "Archived",
}

export const KANBAN_COLUMNS: CampaignStatus[] = [
  "drafted",
  "sent",
  "responded",
  "meeting_scheduled",
]

export const COLLAPSED_COLUMNS: CampaignStatus[] = ["rejected", "archived"]
