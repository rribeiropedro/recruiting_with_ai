"use client"

import { create } from "zustand"
import {
  getJob,
  JobDescriptionResponse,
  JobSubmitPayload,
  matchJob,
  MatchResult,
  submitJob as submitJobRequest,
} from "@/lib/generate/api"

export type JobInputTab = "url" | "paste"

interface JobStore {
  activeTab: JobInputTab
  job: JobDescriptionResponse | null
  match: MatchResult | null
  isSubmitting: boolean
  isRefreshing: boolean
  isMatching: boolean
  error: string | null
  matchError: string | null
  setActiveTab: (tab: JobInputTab) => void
  setError: (message: string | null) => void
  submitJob: (payload: JobSubmitPayload, sourceTab: JobInputTab) => Promise<JobDescriptionResponse | null>
  refreshJob: (id: string) => Promise<JobDescriptionResponse | null>
  loadMatch: (id: string) => Promise<MatchResult | null>
  resetJob: () => void
}

const failedStatuses = new Set(["failed", "error"])

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

export function jobFailureMessage(job: JobDescriptionResponse) {
  if (job.error_message) return job.error_message
  if (job.status && failedStatuses.has(job.status.toLowerCase())) {
    return "Could not analyze this job description."
  }
  return null
}

export const useJobStore = create<JobStore>((set, get) => ({
  activeTab: "url",
  job: null,
  match: null,
  isSubmitting: false,
  isRefreshing: false,
  isMatching: false,
  error: null,
  matchError: null,

  setActiveTab(tab) {
    set({ activeTab: tab, error: null })
  },

  setError(message) {
    set({ error: message })
  },

  async submitJob(payload, sourceTab) {
    set({ job: null, isSubmitting: true, error: null, match: null, matchError: null })
    try {
      const job = await submitJobRequest(payload)
      const failure = jobFailureMessage(job)
      set({
        job,
        error: failure,
        activeTab: failure && job.url ? "paste" : get().activeTab,
        isSubmitting: false,
      })
      return job
    } catch (error) {
      set({
        error: errorMessage(error, "Could not submit this job description."),
        activeTab: sourceTab === "url" ? "paste" : get().activeTab,
        isSubmitting: false,
      })
      return null
    }
  },

  async refreshJob(id) {
    set({ isRefreshing: true, error: null })
    try {
      const job = await getJob(id)
      const failure = jobFailureMessage(job)
      set({
        job,
        error: failure,
        activeTab: failure && job.url ? "paste" : get().activeTab,
        isRefreshing: false,
      })
      return job
    } catch (error) {
      set({
        error: errorMessage(error, "Could not refresh this job analysis."),
        isRefreshing: false,
      })
      return null
    }
  },

  async loadMatch(id) {
    set({ isMatching: true, matchError: null })
    try {
      const match = await matchJob(id)
      set({ match, isMatching: false })
      return match
    } catch (error) {
      set({
        matchError: errorMessage(error, "Could not load the match preview."),
        isMatching: false,
      })
      return null
    }
  },

  resetJob() {
    set({
      job: null,
      match: null,
      error: null,
      matchError: null,
      isSubmitting: false,
      isRefreshing: false,
      isMatching: false,
    })
  },
}))
