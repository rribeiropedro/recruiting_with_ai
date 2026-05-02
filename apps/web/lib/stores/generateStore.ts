"use client"

import { create } from "zustand"
import { createClient } from "@/lib/supabase/client"
import {
  ApplicationDetailResponse,
  ApplicationStatusResponse,
  generateApplication,
  generateFromUrl as generateFromUrlRequest,
  getApplicationDetails,
  getApplicationStatus,
  listApplications,
  regenerateApplication,
  ResumeTemplate,
} from "@/lib/generate/api"

interface GenerateStore {
  currentApplication: ApplicationStatusResponse | null
  applications: ApplicationStatusResponse[]
  selectedApplication: ApplicationDetailResponse | null
  selectedTemplate: ResumeTemplate
  cursor: string | null
  isGenerating: boolean
  isPolling: boolean
  isLoadingApplications: boolean
  isLoadingDetail: boolean
  isSavingTemplate: boolean
  error: string | null
  detailError: string | null
  templateLoaded: boolean

  loadTemplatePreference: () => Promise<void>
  setSelectedTemplate: (template: ResumeTemplate) => Promise<void>
  generateFromJobId: (jobDescriptionId: string, template?: ResumeTemplate) => Promise<void>
  generateFromUrl: (url: string, template?: ResumeTemplate) => Promise<void>
  generateFromText: (text: string, template?: ResumeTemplate) => Promise<void>
  pollStatus: (id: string) => Promise<ApplicationStatusResponse | null>
  fetchApplications: (append?: boolean) => Promise<void>
  fetchApplicationDetails: (id: string) => Promise<void>
  regenerate: (id: string) => Promise<void>
  clearCurrentApplication: () => void
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback
}

function normalizeTemplate(value: unknown): ResumeTemplate {
  return value === "classic" || value === "minimal" ? value : "modern"
}

function mergeApplication(
  applications: ApplicationStatusResponse[],
  application: ApplicationStatusResponse
) {
  const withoutExisting = applications.filter((item) => item.id !== application.id)
  return [application, ...withoutExisting]
}

async function updatePreferredTemplate(template: ResumeTemplate) {
  const supabase = createClient()
  const {
    data: { user },
    error,
  } = await supabase.auth.getUser()
  if (error || !user) return

  const payload = {
    email: user.email ?? "",
    full_name:
      typeof user.user_metadata.full_name === "string"
        ? user.user_metadata.full_name
        : user.email?.split("@")[0] ?? "User",
    preferred_template: template,
    updated_at: new Date().toISOString(),
    user_id: user.id,
  }

  await supabase.from("user_profiles").upsert(payload, { onConflict: "user_id" })
}

export const useGenerateStore = create<GenerateStore>((set, get) => ({
  currentApplication: null,
  applications: [],
  selectedApplication: null,
  selectedTemplate: "modern",
  cursor: null,
  isGenerating: false,
  isPolling: false,
  isLoadingApplications: false,
  isLoadingDetail: false,
  isSavingTemplate: false,
  error: null,
  detailError: null,
  templateLoaded: false,

  async loadTemplatePreference() {
    if (get().templateLoaded) return
    const supabase = createClient()
    const {
      data: { user },
    } = await supabase.auth.getUser()
    if (!user) {
      set({ templateLoaded: true })
      return
    }

    const { data } = await supabase
      .from("user_profiles")
      .select("preferred_template")
      .eq("user_id", user.id)
      .maybeSingle()

    set({
      selectedTemplate: normalizeTemplate(data?.preferred_template),
      templateLoaded: true,
    })
  },

  async setSelectedTemplate(template) {
    set({ selectedTemplate: template, isSavingTemplate: true })
    try {
      await updatePreferredTemplate(template)
    } finally {
      set({ isSavingTemplate: false, templateLoaded: true })
    }
  },

  async generateFromJobId(jobDescriptionId, template) {
    set({ error: null, isGenerating: true })
    try {
      const selectedTemplate = template ?? get().selectedTemplate
      await updatePreferredTemplate(selectedTemplate)
      const response = await generateApplication({
        job_description_id: jobDescriptionId,
        template: selectedTemplate,
      })
      const application = await getApplicationStatus(response.application_id)
      set((state) => ({
        applications: mergeApplication(state.applications, application),
        currentApplication: application,
        isGenerating: false,
      }))
    } catch (error) {
      set({
        error: errorMessage(error, "Could not start resume generation."),
        isGenerating: false,
      })
    }
  },

  async generateFromUrl(url, template) {
    set({ error: null, isGenerating: true })
    try {
      const selectedTemplate = template ?? get().selectedTemplate
      const response = await generateFromUrlRequest({ template: selectedTemplate, url })
      const application = await getApplicationStatus(response.application_id)
      set((state) => ({
        applications: mergeApplication(state.applications, application),
        currentApplication: application,
        isGenerating: false,
      }))
    } catch (error) {
      set({
        error: errorMessage(error, "Could not start resume generation."),
        isGenerating: false,
      })
    }
  },

  async generateFromText(text, template) {
    set({ error: null, isGenerating: true })
    try {
      const selectedTemplate = template ?? get().selectedTemplate
      const response = await generateFromUrlRequest({ raw_text: text, template: selectedTemplate })
      const application = await getApplicationStatus(response.application_id)
      set((state) => ({
        applications: mergeApplication(state.applications, application),
        currentApplication: application,
        isGenerating: false,
      }))
    } catch (error) {
      set({
        error: errorMessage(error, "Could not start resume generation."),
        isGenerating: false,
      })
    }
  },

  async pollStatus(id) {
    set({ isPolling: true })
    try {
      const application = await getApplicationStatus(id)
      set((state) => ({
        applications: mergeApplication(state.applications, application),
        currentApplication:
          state.currentApplication?.id === id || !state.currentApplication
            ? application
            : state.currentApplication,
        isPolling: false,
      }))
      return application
    } catch (error) {
      set({
        error: errorMessage(error, "Could not refresh generation status."),
        isPolling: false,
      })
      return null
    }
  },

  async fetchApplications(append = false) {
    set({ isLoadingApplications: true, error: null })
    try {
      const response = await listApplications({
        cursor: append ? get().cursor : null,
        limit: 10,
      })
      set((state) => ({
        applications: append ? [...state.applications, ...response.applications] : response.applications,
        cursor: response.cursor,
        isLoadingApplications: false,
      }))
    } catch (error) {
      set({
        error: errorMessage(error, "Could not load generated applications."),
        isLoadingApplications: false,
      })
    }
  },

  async fetchApplicationDetails(id) {
    set({ detailError: null, isLoadingDetail: true, selectedApplication: null })
    try {
      const detail = await getApplicationDetails(id)
      set({ isLoadingDetail: false, selectedApplication: detail })
    } catch (error) {
      set({
        detailError: errorMessage(error, "Could not load application details."),
        isLoadingDetail: false,
      })
    }
  },

  async regenerate(id) {
    set({ error: null, isGenerating: true })
    try {
      const response = await regenerateApplication(id)
      const application = await getApplicationStatus(response.application_id)
      set((state) => ({
        applications: mergeApplication(state.applications, application),
        currentApplication: application,
        isGenerating: false,
      }))
    } catch (error) {
      set({
        error: errorMessage(error, "Could not regenerate this resume."),
        isGenerating: false,
      })
    }
  },

  clearCurrentApplication() {
    set({ currentApplication: null, error: null })
  },
}))
