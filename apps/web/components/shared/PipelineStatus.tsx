"use client"

import Link from "next/link"
import { useEffect } from "react"
import { BriefcaseBusiness, CheckCircle2, Database, FileCheck2, Loader2, Send } from "lucide-react"
import { usePipelineStore } from "@/lib/stores/pipelineStore"

function relativeTime(value: string) {
  const diff = Date.now() - new Date(value).getTime()
  const minutes = Math.max(1, Math.round(diff / 60_000))
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  return `${days}d ago`
}

export function PipelineStatus() {
  const status = usePipelineStore((state) => state.status)
  const isLoading = usePipelineStore((state) => state.isLoading)
  const error = usePipelineStore((state) => state.error)
  const fetchPipelineStatus = usePipelineStore((state) => state.fetchPipelineStatus)

  useEffect(() => {
    void fetchPipelineStatus()

    function handleFocus() {
      void fetchPipelineStatus()
    }

    window.addEventListener("focus", handleFocus)
    return () => window.removeEventListener("focus", handleFocus)
  }, [fetchPipelineStatus])

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-slate-950">Your Pipeline</h2>
        {isLoading ? <Loader2 className="h-4 w-4 animate-spin text-slate-500" /> : null}
      </div>

      {error ? <p className="mt-3 text-xs leading-5 text-red-600">{error}</p> : null}

      <div className="mt-4 space-y-3">
        <Link href="/vault" className="flex items-center justify-between gap-3 rounded-md p-1 hover:bg-slate-50">
          <span className="flex min-w-0 items-center gap-2 text-sm text-slate-700">
            <Database className="h-4 w-4 shrink-0 text-slate-500" />
            <span>Vault</span>
          </span>
          <span className="flex shrink-0 items-center gap-2 text-xs font-medium text-slate-600">
            {status ? `${status.vault_node_count} nodes` : "--"}
            {status?.vault_node_count ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : null}
          </span>
        </Link>

        <Link href="/generate" className="flex items-center justify-between gap-3 rounded-md p-1 hover:bg-slate-50">
          <span className="flex min-w-0 items-center gap-2 text-sm text-slate-700">
            <FileCheck2 className="h-4 w-4 shrink-0 text-slate-500" />
            <span>Last resume</span>
          </span>
          <span className="flex min-w-0 shrink-0 items-center gap-2 text-xs font-medium text-slate-600">
            {status?.last_application ? (
              <>
                <span className="max-w-24 truncate">{status.last_application.company_name ?? "Company"}</span>
                <span>{relativeTime(status.last_application.created_at)}</span>
                <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
              </>
            ) : (
              "--"
            )}
          </span>
        </Link>

        <Link href="/outreach" className="flex items-center justify-between gap-3 rounded-md p-1 hover:bg-slate-50">
          <span className="flex min-w-0 items-center gap-2 text-sm text-slate-700">
            <Send className="h-4 w-4 shrink-0 text-slate-500" />
            <span>Outreach</span>
          </span>
          <span className="flex shrink-0 items-center gap-2 text-xs font-medium text-slate-600">
            {status ? `${status.outreach_counts.sent} sent` : "--"}
            {status?.outreach_counts.responded ? (
              <span className="inline-flex items-center gap-1 text-emerald-700">
                <BriefcaseBusiness className="h-3.5 w-3.5" />
                {status.outreach_counts.responded}
              </span>
            ) : null}
          </span>
        </Link>
      </div>
    </section>
  )
}
