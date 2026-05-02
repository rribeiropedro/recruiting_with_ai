"use client"

import { useEffect } from "react"
import Link from "next/link"
import { AlertTriangle, Calendar, ExternalLink, Loader2 } from "lucide-react"
import { getApplicationPdf } from "@/lib/generate/api"
import type { ApplicationStatusResponse } from "@/lib/generate/api"
import { useGenerateStore } from "@/lib/stores/generateStore"
import { ApplicationDetail } from "@/components/generate/ApplicationDetail"

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(value))
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    cache_hit: "Ready",
    completed: "Ready",
    extracting: "Analyzing",
    failed: "Failed",
    matching: "Matching",
    pending: "Queued",
    rendering: "Rendering",
    rewriting: "Tailoring",
    scraping: "Reading",
  }
  return labels[status] ?? "Working"
}

function badgeClass(status: string) {
  if (status === "failed") return "bg-red-50 text-red-700"
  if (status === "completed" || status === "cache_hit") return "bg-emerald-50 text-emerald-700"
  return "bg-blue-50 text-blue-700"
}

function titleFor(application: ApplicationStatusResponse) {
  return [application.company_name, application.role_title].filter(Boolean).join(" - ") || "Generated application"
}

export function ApplicationHistory({ compact = false }: { compact?: boolean }) {
  const applications = useGenerateStore((state) => state.applications)
  const cursor = useGenerateStore((state) => state.cursor)
  const detailError = useGenerateStore((state) => state.detailError)
  const error = useGenerateStore((state) => state.error)
  const isLoadingApplications = useGenerateStore((state) => state.isLoadingApplications)
  const isLoadingDetail = useGenerateStore((state) => state.isLoadingDetail)
  const selectedApplication = useGenerateStore((state) => state.selectedApplication)
  const fetchApplications = useGenerateStore((state) => state.fetchApplications)
  const fetchApplicationDetails = useGenerateStore((state) => state.fetchApplicationDetails)

  useEffect(() => {
    void fetchApplications(false)
  }, [fetchApplications])

  async function openPdf(application: ApplicationStatusResponse) {
    const response = await getApplicationPdf(application.id)
    window.open(response.url, "_blank", "noopener,noreferrer")
  }

  return (
    <section className={compact ? "space-y-4" : "grid gap-5 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]"}>
      <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 pb-5">
          <div>
            <h2 className="text-xl font-semibold tracking-normal text-slate-950">Application history</h2>
            <p className="mt-1 text-sm text-slate-600">Generated resumes sorted by newest first.</p>
          </div>
          {isLoadingApplications ? <Loader2 className="h-5 w-5 animate-spin text-slate-500" /> : null}
        </div>

        {error ? (
          <div className="mt-5 flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        {!isLoadingApplications && applications.length === 0 ? (
          <div className="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
            No generated applications yet.
          </div>
        ) : (
          <div className="mt-5 divide-y divide-slate-200">
            {applications.map((application) => (
              <article key={application.id} className="py-4 first:pt-0 last:pb-0">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <h3 className="truncate text-base font-semibold text-slate-950">{titleFor(application)}</h3>
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                      <span className={`rounded-full px-2.5 py-1 font-medium ${badgeClass(application.status)}`}>
                        {statusLabel(application.status)}
                      </span>
                      {application.cache_hit ? (
                        <span className="rounded-full bg-amber-50 px-2.5 py-1 font-medium text-amber-800">
                          Cache hit
                        </span>
                      ) : null}
                      <span className="inline-flex items-center gap-1">
                        <Calendar className="h-3.5 w-3.5" />
                        {formatDate(application.created_at)}
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {compact ? (
                      <Link
                        href="/generate/history"
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                      >
                        View details
                      </Link>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void fetchApplicationDetails(application.id)}
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
                      >
                        View details
                      </button>
                    )}
                    {application.status === "completed" || application.status === "cache_hit" ? (
                      <button
                        type="button"
                        onClick={() => void openPdf(application)}
                        className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
                      >
                        <ExternalLink className="h-4 w-4" />
                        View PDF
                      </button>
                    ) : null}
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}

        {cursor ? (
          <div className="mt-5 flex justify-center">
            <button
              type="button"
              onClick={() => void fetchApplications(true)}
              disabled={isLoadingApplications}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              Load more
            </button>
          </div>
        ) : null}
      </div>

      {!compact ? (
        <div className="space-y-3">
          {detailError ? (
            <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{detailError}</span>
            </div>
          ) : null}
          <ApplicationDetail application={selectedApplication} isLoading={isLoadingDetail} />
        </div>
      ) : null}
    </section>
  )
}
