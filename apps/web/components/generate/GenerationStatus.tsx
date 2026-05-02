"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { useEffect, useMemo, useState } from "react"
import {
  AlertTriangle,
  CheckCircle2,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  RefreshCcw,
  Send,
} from "lucide-react"
import { ApplicationStatusResponse, getApplicationPdf } from "@/lib/generate/api"
import { useGenerateStore } from "@/lib/stores/generateStore"

const steps = [
  { key: "scraping", label: "Reading the job posting" },
  { key: "extracting", label: "Analyzing what they're looking for" },
  { key: "matching", label: "Finding your best experience" },
  { key: "rewriting", label: "Tailoring your resume" },
  { key: "rendering", label: "Creating your PDF" },
  { key: "completed", label: "Your resume is ready" },
]

const statusIndex: Record<string, number> = {
  pending: 0,
  scraping: 0,
  extracting: 1,
  matching: 2,
  rewriting: 3,
  rendering: 4,
  cache_hit: 5,
  completed: 5,
  failed: -1,
}

function statusLabel(status: string) {
  if (status === "failed") return "Something went wrong"
  if (status === "pending") return "Queued"
  return steps[statusIndex[status]]?.label ?? "Working"
}

function isFinished(application: ApplicationStatusResponse) {
  return application.status === "completed" || application.status === "failed" || application.status === "cache_hit"
}

export function GenerationStatus({ application }: { application: ApplicationStatusResponse | null }) {
  const router = useRouter()
  const error = useGenerateStore((state) => state.error)
  const isGenerating = useGenerateStore((state) => state.isGenerating)
  const isPolling = useGenerateStore((state) => state.isPolling)
  const pollStatus = useGenerateStore((state) => state.pollStatus)
  const regenerate = useGenerateStore((state) => state.regenerate)

  const [pdfUrl, setPdfUrl] = useState<string | null>(application?.pdf_url ?? null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [isPreparingDownload, setIsPreparingDownload] = useState(false)
  const [isStartingOutreach, setIsStartingOutreach] = useState(false)

  const currentStep = application ? statusIndex[application.status] ?? 0 : 0
  const ready = application?.status === "completed" || application?.status === "cache_hit"

  useEffect(() => {
    setPdfUrl(application?.pdf_url ?? null)
  }, [application?.id, application?.pdf_url])

  useEffect(() => {
    if (!application || isFinished(application)) return

    const interval = window.setInterval(() => {
      void pollStatus(application.id)
    }, 3000)

    return () => window.clearInterval(interval)
  }, [application, pollStatus])

  useEffect(() => {
    if (!application || !ready || pdfUrl) return
    void getApplicationPdf(application.id)
      .then((response) => setPdfUrl(response.url))
      .catch(() => undefined)
  }, [application, pdfUrl, ready])

  const title = useMemo(() => {
    if (!application) return "Resume generation"
    return [application.company_name, application.role_title].filter(Boolean).join(" - ") || "Resume generation"
  }, [application])

  async function handleDownload() {
    if (!application) return
    setActionError(null)
    setIsPreparingDownload(true)
    try {
      const response = await getApplicationPdf(application.id)
      setPdfUrl(response.url)
      window.open(response.url, "_blank", "noopener,noreferrer")
    } catch (downloadError) {
      setActionError(downloadError instanceof Error ? downloadError.message : "Could not prepare the PDF.")
    } finally {
      setIsPreparingDownload(false)
    }
  }

  async function handleStartOutreach() {
    if (!application) return
    setActionError(null)
    setIsStartingOutreach(true)
    try {
      const response = await fetch("/api/outreach/campaigns", {
        body: JSON.stringify({ application_id: application.id, auto_discover_contact: true }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      })
      if (!response.ok) {
        const text = await response.text()
        throw new Error(text || "Could not start outreach.")
      }
      router.push("/outreach")
    } catch (outreachError) {
      setActionError(outreachError instanceof Error ? outreachError.message : "Could not start outreach.")
      setIsStartingOutreach(false)
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-normal text-slate-950">Generation status</h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">{title}</p>
        </div>
        {isPolling ? (
          <span className="inline-flex w-fit items-center gap-2 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" />
            Updating
          </span>
        ) : null}
      </div>

      {!application ? (
        <div className="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center">
          <FileText className="mx-auto h-8 w-8 text-slate-400" />
          <p className="mt-3 text-sm font-medium text-slate-900">No resume generation running</p>
          <p className="mt-1 text-sm text-slate-500">Choose a processed job and template to start.</p>
        </div>
      ) : (
        <div className="mt-5 space-y-5">
          <div className="grid gap-3 md:grid-cols-6">
            {steps.map((step, index) => {
              const isComplete = currentStep >= index && application.status !== "failed"
              const isActive = currentStep === index && application.status !== "completed"
              return (
                <div
                  key={step.key}
                  className={`rounded-lg border p-3 ${
                    isComplete ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {isComplete ? (
                      <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-700" />
                    ) : isActive ? (
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-slate-500" />
                    ) : (
                      <span className="h-4 w-4 rounded-full border border-slate-300" />
                    )}
                    <span className="text-xs font-medium leading-5 text-slate-700">{step.label}</span>
                  </div>
                </div>
              )
            })}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                application.status === "failed"
                  ? "bg-red-50 text-red-700"
                  : ready
                    ? "bg-emerald-50 text-emerald-700"
                    : "bg-blue-50 text-blue-700"
              }`}
            >
              {statusLabel(application.status)}
            </span>
            {application.cache_hit ? (
              <span className="rounded-full bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-800">
                Served from cache - a similar resume was generated previously
              </span>
            ) : null}
            <span className="text-xs text-slate-500">
              {application.matched_node_count} matched {application.matched_node_count === 1 ? "node" : "nodes"}
            </span>
          </div>

          {application.status === "failed" ? (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">Something went wrong</p>
                <p className="mt-1">{application.error_message ?? "Try again when the service is ready."}</p>
              </div>
            </div>
          ) : null}

          {ready ? (
            <div className="space-y-4">
              {pdfUrl ? (
                <>
                  <div className="hidden overflow-hidden rounded-lg border border-slate-200 md:block">
                    <iframe title="Generated resume preview" src={pdfUrl} className="h-[640px] w-full bg-white" />
                  </div>
                  <a
                    href={pdfUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 md:hidden"
                  >
                    <ExternalLink className="h-4 w-4" />
                    View Resume
                  </a>
                </>
              ) : (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                  Preparing preview
                </div>
              )}

              <div className="flex flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={() => void handleDownload()}
                  disabled={isPreparingDownload}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isPreparingDownload ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Download className="h-4 w-4" />
                  )}
                  Download
                </button>
                <button
                  type="button"
                  onClick={() => void handleStartOutreach()}
                  disabled={isStartingOutreach}
                  className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isStartingOutreach ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  Send to Hiring Manager
                </button>
                {application.cache_hit ? (
                  <button
                    type="button"
                    onClick={() => void regenerate(application.id)}
                    disabled={isGenerating}
                    className="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2 text-sm font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
                    Regenerate
                  </button>
                ) : null}
              </div>
            </div>
          ) : null}

          {application.status === "failed" ? (
            <button
              type="button"
              onClick={() => void regenerate(application.id)}
              disabled={isGenerating}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isGenerating ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              Try Again
            </button>
          ) : null}
        </div>
      )}

      {error ? (
        <div className="mt-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      {actionError ? (
        <div className="mt-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{actionError}</span>
        </div>
      ) : null}

      <div className="mt-5">
        <Link href="/generate/history" className="text-sm font-medium text-slate-700 hover:text-slate-950">
          View all generated applications
        </Link>
      </div>
    </section>
  )
}
