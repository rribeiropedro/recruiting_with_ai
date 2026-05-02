"use client"

import { create } from "zustand"
import { getPipelineStatus, PipelineStatusResponse } from "@/lib/generate/api"

const STALE_AFTER_MS = 5 * 60 * 1000

interface PipelineStore {
  status: PipelineStatusResponse | null
  isLoading: boolean
  error: string | null
  fetchedAt: number | null
  fetchPipelineStatus: (force?: boolean) => Promise<void>
}

function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Could not load pipeline status."
}

export const usePipelineStore = create<PipelineStore>((set, get) => ({
  status: null,
  isLoading: false,
  error: null,
  fetchedAt: null,

  async fetchPipelineStatus(force = false) {
    const { fetchedAt, isLoading } = get()
    if (isLoading) return
    if (!force && fetchedAt && Date.now() - fetchedAt < STALE_AFTER_MS) return

    set({ error: null, isLoading: true })
    try {
      const status = await getPipelineStatus()
      set({ fetchedAt: Date.now(), isLoading: false, status })
    } catch (error) {
      set({ error: errorMessage(error), isLoading: false })
    }
  },
}))
