"use client"

import { FormEvent, useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  BriefcaseBusiness,
  Building2,
  CheckCircle2,
  Clipboard,
  FileText,
  Link as LinkIcon,
  Loader2,
  RotateCcw,
  Wand2,
} from "lucide-react"
import { jobFailureMessage, useJobStore } from "@/lib/stores/jobStore"

function validateHttpsUrl(value: string) {
  try {
    const parsed = new URL(value)
    return parsed.protocol === "https:"
  } catch {
    return false
  }
}

function uniqueSkills(skills: string[]) {
  return Array.from(new Set(skills.map((skill) => skill.trim()).filter(Boolean)))
}

export function JobInput() {
  const activeTab = useJobStore((state) => state.activeTab)
  const job = useJobStore((state) => state.job)
  const match = useJobStore((state) => state.match)
  const isSubmitting = useJobStore((state) => state.isSubmitting)
  const isRefreshing = useJobStore((state) => state.isRefreshing)
  const isMatching = useJobStore((state) => state.isMatching)
  const error = useJobStore((state) => state.error)
  const matchError = useJobStore((state) => state.matchError)
  const setActiveTab = useJobStore((state) => state.setActiveTab)
  const setError = useJobStore((state) => state.setError)
  const submitJob = useJobStore((state) => state.submitJob)
  const refreshJob = useJobStore((state) => state.refreshJob)
  const loadMatch = useJobStore((state) => state.loadMatch)
  const resetJob = useJobStore((state) => state.resetJob)

  const [url, setUrl] = useState("")
  const [rawText, setRawText] = useState("")
  const [matchRequestedFor, setMatchRequestedFor] = useState<string | null>(null)

  const failure = job ? jobFailureMessage(job) : null
  const isProcessing = Boolean(job && !job.is_embedded && !failure)
  const technicalSkills = useMemo(
    () => uniqueSkills(job?.requirements?.technical_skills ?? []),
    [job?.requirements?.technical_skills]
  )

  useEffect(() => {
    if (!job || job.is_embedded || failure) return

    const interval = window.setInterval(() => {
      void refreshJob(job.id)
    }, 3000)

    return () => window.clearInterval(interval)
  }, [failure, job, refreshJob])

  useEffect(() => {
    if (!job?.is_embedded || matchRequestedFor === job.id) return
    setMatchRequestedFor(job.id)
    void loadMatch(job.id)
  }, [job?.id, job?.is_embedded, loadMatch, matchRequestedFor])

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    if (activeTab === "url") {
      const trimmed = url.trim()
      if (!trimmed) {
        setError("Enter a job posting URL.")
        return
      }
      if (!validateHttpsUrl(trimmed)) {
        setError("Job URLs must start with https://.")
        return
      }
      const submitted = await submitJob({ url: trimmed }, "url")
      if (submitted) setMatchRequestedFor(null)
      return
    }

    const trimmed = rawText.trim()
    if (trimmed.length < 100) {
      setError("Paste at least 100 characters from the job description.")
      return
    }
    const submitted = await submitJob({ raw_text: trimmed }, "paste")
    if (submitted) setMatchRequestedFor(null)
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-4 border-b border-slate-200 pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-normal text-slate-950">Job input</h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Analyze a job description before matching it to your Experience Vault.
          </p>
        </div>
        {job ? (
          <button
            type="button"
            onClick={() => {
              resetJob()
              setMatchRequestedFor(null)
            }}
            className="inline-flex w-fit items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            <RotateCcw className="h-4 w-4" />
            New job
          </button>
        ) : null}
      </div>

      <form onSubmit={handleSubmit} className="mt-5 space-y-5">
        <div className="inline-flex rounded-lg border border-slate-300 bg-slate-100 p-1">
          <button
            type="button"
            onClick={() => setActiveTab("url")}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
              activeTab === "url"
                ? "bg-white text-slate-950 shadow-sm"
                : "text-slate-600 hover:text-slate-950"
            }`}
          >
            <LinkIcon className="h-4 w-4" />
            URL
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("paste")}
            className={`inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium ${
              activeTab === "paste"
                ? "bg-white text-slate-950 shadow-sm"
                : "text-slate-600 hover:text-slate-950"
            }`}
          >
            <Clipboard className="h-4 w-4" />
            Paste
          </button>
        </div>

        {activeTab === "url" ? (
          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-900">Job URL</span>
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://company.com/careers/software-engineer"
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
            />
          </label>
        ) : (
          <label className="block space-y-2">
            <span className="text-sm font-medium text-slate-900">Job description</span>
            <textarea
              value={rawText}
              onChange={(event) => setRawText(event.target.value)}
              rows={10}
              className="min-h-64 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm leading-6 outline-none focus:border-slate-900"
            />
          </label>
        )}

        {error ? (
          <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="submit"
            disabled={isSubmitting}
            className="inline-flex w-fit items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
            {isSubmitting ? "Analyzing..." : "Analyze"}
          </button>
          {isRefreshing ? (
            <span className="inline-flex items-center gap-2 text-sm text-slate-500" aria-live="polite">
              <Loader2 className="h-4 w-4 animate-spin" />
              Updating status
            </span>
          ) : null}
        </div>
      </form>

      {isProcessing ? (
        <div className="mt-6 flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800">
          <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin" />
          <div>
            <p className="font-medium">Analyzing job description</p>
            <p className="mt-1 text-blue-700">Extracting company, role, and requirements.</p>
          </div>
        </div>
      ) : null}

      {job?.is_embedded ? (
        <div className="mt-6 space-y-5 border-t border-slate-200 pt-5">
          <div className="flex items-center gap-2 text-sm font-medium text-emerald-700">
            <CheckCircle2 className="h-4 w-4" />
            Processed
          </div>

          {match?.low_relevance_warning ? (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                Your Experience Vault may not contain directly relevant experience for this role.
                The generated resume will use your closest matches, but consider adding more relevant
                nodes to your Vault.
              </span>
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                <Building2 className="h-4 w-4" />
                Company
              </div>
              <p className="mt-1 truncate text-base font-semibold text-slate-950">
                {job.company_name || job.requirements.company_name || "Company not detected"}
              </p>
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
                <BriefcaseBusiness className="h-4 w-4" />
                Role
              </div>
              <p className="mt-1 truncate text-base font-semibold text-slate-950">
                {job.role_title || job.requirements.role_title || "Role not detected"}
              </p>
            </div>
          </div>

          <div>
            <p className="text-sm font-medium text-slate-900">Technical skills</p>
            {technicalSkills.length ? (
              <div className="mt-3 flex flex-wrap gap-2">
                {technicalSkills.slice(0, 12).map((skill) => (
                  <span
                    key={skill}
                    className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">No technical skills extracted.</p>
            )}
          </div>

          {isMatching ? (
            <div className="inline-flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              Checking Vault relevance
            </div>
          ) : null}

          {matchError ? (
            <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{matchError}</span>
            </div>
          ) : null}

          <form action="/generate" method="get" className="flex justify-end">
            <input type="hidden" name="job_description_id" value={job.id} />
            <button
              type="submit"
              className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              <FileText className="h-4 w-4" />
              Generate Resume
            </button>
          </form>
        </div>
      ) : null}
    </section>
  )
}
