"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle, ExternalLink, Loader2 } from "lucide-react"
import { ApplicationDetailResponse, getApplicationPdf, MatchedApplicationNode } from "@/lib/generate/api"

function scoreLabel(score: number | undefined) {
  if (typeof score !== "number" || Number.isNaN(score)) return null
  return `${Math.round(score * 100)}% match`
}

function nodeTitle(node: MatchedApplicationNode, index: number) {
  return node.title ?? node.role ?? node.organization ?? `Matched experience ${index + 1}`
}

function bulletsFor(node: MatchedApplicationNode) {
  return node.rewritten_bullets ?? node.bullet_points ?? []
}

export function ApplicationDetail({
  application,
  isLoading,
}: {
  application: ApplicationDetailResponse | null
  isLoading: boolean
}) {
  const [pdfUrl, setPdfUrl] = useState<string | null>(application?.pdf_url ?? null)
  const [pdfError, setPdfError] = useState<string | null>(null)

  useEffect(() => {
    setPdfUrl(application?.pdf_url ?? null)
    setPdfError(null)
  }, [application?.id, application?.pdf_url])

  useEffect(() => {
    if (
      !application ||
      (application.status !== "completed" && application.status !== "cache_hit") ||
      pdfUrl
    ) {
      return
    }
    void getApplicationPdf(application.id)
      .then((response) => setPdfUrl(response.url))
      .catch((error) => setPdfError(error instanceof Error ? error.message : "Could not load PDF preview."))
  }, [application, pdfUrl])

  const requirements = useMemo(() => {
    if (!application?.job_requirements) return []
    return Object.entries(application.job_requirements).filter(([, value]) => {
      if (Array.isArray(value)) return value.length > 0
      return value !== null && value !== undefined && value !== ""
    })
  }, [application?.job_requirements])

  if (isLoading) {
    return (
      <section className="rounded-lg border border-slate-200 bg-white p-5 text-slate-500">
        <Loader2 className="h-5 w-5 animate-spin" />
      </section>
    )
  }

  if (!application) {
    return (
      <section className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-500">
        Select an application to inspect its matched experience and preview.
      </section>
    )
  }

  return (
    <section className="space-y-5 rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-200 pb-5 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-normal text-slate-950">
            {[application.company_name, application.role_title].filter(Boolean).join(" - ") || "Application"}
          </h2>
          <p className="mt-1 text-sm text-slate-600">
            {application.matched_node_count} matched{" "}
            {application.matched_node_count === 1 ? "experience" : "experiences"}
          </p>
        </div>
        {pdfUrl ? (
          <a
            href={pdfUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex w-fit items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50"
          >
            <ExternalLink className="h-4 w-4" />
            Open PDF
          </a>
        ) : null}
      </div>

      {pdfUrl ? (
        <div className="hidden overflow-hidden rounded-lg border border-slate-200 lg:block">
          <iframe title="Application PDF preview" src={pdfUrl} className="h-[560px] w-full bg-white" />
        </div>
      ) : null}

      {pdfError ? (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{pdfError}</span>
        </div>
      ) : null}

      {application.matched_nodes.length ? (
        <div>
          <h3 className="text-sm font-semibold uppercase text-slate-500">Matched experience</h3>
          <div className="mt-3 space-y-3">
            {application.matched_nodes.map((node, index) => (
              <article key={String(node.id ?? node.node_id ?? index)} className="rounded-lg border border-slate-200 p-4">
                <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h4 className="text-base font-semibold text-slate-950">{nodeTitle(node, index)}</h4>
                    <p className="mt-1 text-sm text-slate-600">
                      {[node.organization, node.role].filter(Boolean).join(" - ") || "Experience Vault"}
                    </p>
                  </div>
                  {scoreLabel(application.similarity_scores[index]) ? (
                    <span className="w-fit rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700">
                      {scoreLabel(application.similarity_scores[index])}
                    </span>
                  ) : null}
                </div>
                {node.description ? (
                  <p className="mt-3 text-sm leading-6 text-slate-700">{node.description}</p>
                ) : null}
                {bulletsFor(node).length ? (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-sm leading-6 text-slate-700">
                    {bulletsFor(node).slice(0, 4).map((bullet, bulletIndex) => (
                      <li key={`${String(node.id ?? index)}-${bulletIndex}`}>{bullet}</li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
          </div>
        </div>
      ) : null}

      {requirements.length ? (
        <div>
          <h3 className="text-sm font-semibold uppercase text-slate-500">Job requirements</h3>
          <dl className="mt-3 grid gap-3 sm:grid-cols-2">
            {requirements.slice(0, 8).map(([key, value]) => (
              <div key={key} className="rounded-lg border border-slate-200 p-3">
                <dt className="text-xs font-medium uppercase text-slate-500">{key.replaceAll("_", " ")}</dt>
                <dd className="mt-1 text-sm text-slate-800">
                  {Array.isArray(value) ? value.join(", ") : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ) : null}
    </section>
  )
}
