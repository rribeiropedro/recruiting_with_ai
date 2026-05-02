"use client"

import { useEffect, useMemo } from "react"
import { useSearchParams } from "next/navigation"
import { AlertTriangle, FileText, Loader2, Wand2 } from "lucide-react"
import { JobInput } from "@/components/generate/JobInput"
import { TemplatePicker } from "@/components/generate/TemplatePicker"
import { GenerationStatus } from "@/components/generate/GenerationStatus"
import { ApplicationHistory } from "@/components/generate/ApplicationHistory"
import { useGenerateStore } from "@/lib/stores/generateStore"
import { useJobStore } from "@/lib/stores/jobStore"

export function GenerateWorkspace() {
  const searchParams = useSearchParams()
  const queryJobId = searchParams.get("job_description_id")
  const job = useJobStore((state) => state.job)
  const match = useJobStore((state) => state.match)
  const matchError = useJobStore((state) => state.matchError)

  const currentApplication = useGenerateStore((state) => state.currentApplication)
  const error = useGenerateStore((state) => state.error)
  const isGenerating = useGenerateStore((state) => state.isGenerating)
  const isSavingTemplate = useGenerateStore((state) => state.isSavingTemplate)
  const selectedTemplate = useGenerateStore((state) => state.selectedTemplate)
  const generateFromJobId = useGenerateStore((state) => state.generateFromJobId)
  const loadTemplatePreference = useGenerateStore((state) => state.loadTemplatePreference)
  const setSelectedTemplate = useGenerateStore((state) => state.setSelectedTemplate)

  useEffect(() => {
    void loadTemplatePreference()
  }, [loadTemplatePreference])

  const jobId = queryJobId ?? (job?.is_embedded ? job.id : null)
  const canGenerate = Boolean(jobId)
  const roleContext = useMemo(() => {
    if (!job) return null
    return [job.company_name ?? job.requirements.company_name, job.role_title ?? job.requirements.role_title]
      .filter(Boolean)
      .join(" - ")
  }, [job])

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <h1 className="text-3xl font-semibold tracking-normal">Generate</h1>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Start with a target role, then generate a tailored resume.
          </p>
        </header>

        <JobInput />

        <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-3 border-b border-slate-200 pb-5 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h2 className="text-xl font-semibold tracking-normal text-slate-950">Resume template</h2>
              <p className="mt-1 text-sm leading-6 text-slate-600">
                {roleContext ?? "Select a processed job before generating a resume."}
              </p>
            </div>
            {isSavingTemplate ? (
              <span className="inline-flex w-fit items-center gap-2 text-sm text-slate-500">
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving
              </span>
            ) : null}
          </div>

          <div className="mt-5">
            <TemplatePicker
              disabled={isGenerating}
              selected={selectedTemplate}
              onChange={(template) => void setSelectedTemplate(template)}
            />
          </div>

          {match?.low_relevance_warning ? (
            <div className="mt-5 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>The generated resume will use your closest Vault matches for this role.</span>
            </div>
          ) : null}

          {matchError ? (
            <div className="mt-5 flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{matchError}</span>
            </div>
          ) : null}

          <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <button
              type="button"
              disabled={!canGenerate || isGenerating}
              onClick={() => {
                if (jobId) void generateFromJobId(jobId, selectedTemplate)
              }}
              className="inline-flex w-fit items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
              {isGenerating ? "Generating..." : "Generate Resume"}
            </button>

            {!canGenerate ? (
              <span className="inline-flex items-center gap-2 text-sm text-slate-500">
                <FileText className="h-4 w-4" />
                Waiting for a processed job
              </span>
            ) : null}
          </div>

          {error ? (
            <div className="mt-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          ) : null}
        </section>

        <GenerationStatus application={currentApplication} />

        <ApplicationHistory compact />
      </div>
    </main>
  )
}
