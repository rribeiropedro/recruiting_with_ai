"use client"

import Link from "next/link"
import { useParams, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { Archive, ArrowLeft, Loader2, Trash2, X } from "lucide-react"
import { NodeForm } from "@/components/vault/NodeForm"
import { useVaultStore } from "@/lib/stores/vaultStore"
import { getNode, NodePayload, NodeResponse } from "@/lib/vault/api"

const contentFields: Array<keyof NodePayload> = [
  "title",
  "organization",
  "role",
  "description",
  "bullet_points",
]

function contentChanged(before: NodeResponse, after: NodePayload) {
  return contentFields.some((field) => JSON.stringify(before[field] ?? null) !== JSON.stringify(after[field] ?? null))
}

export default function EditVaultNodePage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const updateNode = useVaultStore((state) => state.updateNode)
  const archiveNode = useVaultStore((state) => state.archiveNode)
  const [node, setNode] = useState<NodeResponse | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [showArchiveConfirm, setShowArchiveConfirm] = useState(false)
  const [isArchiving, setIsArchiving] = useState(false)

  useEffect(() => {
    let active = true
    setIsLoading(true)
    getNode(params.id)
      .then((response) => {
        if (!active) return
        setNode(response)
        setError(null)
      })
      .catch((loadError) => {
        if (!active) return
        setError(loadError instanceof Error ? loadError.message : "Could not load this node.")
      })
      .finally(() => {
        if (active) setIsLoading(false)
      })
    return () => {
      active = false
    }
  }, [params.id])

  async function handleSubmit(payload: NodePayload) {
    if (!node) return
    const reprocess = contentChanged(node, payload)
    const updated = await updateNode(node.id, payload)
    setNode(updated)
    setMessage(reprocess ? "Saved. Matching data is refreshing." : "Saved.")
  }

  async function handleArchive() {
    if (!node) return
    setIsArchiving(true)
    try {
      await archiveNode(node.id)
      router.push("/vault")
    } catch (archiveError) {
      setError(archiveError instanceof Error ? archiveError.message : "Could not archive this node.")
      setIsArchiving(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <Link href="/vault" className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-950">
          <ArrowLeft className="h-4 w-4" />
          Back to Vault
        </Link>

        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">Edit Experience Node</h1>
            <p className="mt-1 text-sm text-slate-600">Update the original source material used for matching.</p>
          </div>
          {node ? (
            <button
              type="button"
              onClick={() => setShowArchiveConfirm(true)}
              className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
            >
              <Archive className="h-4 w-4" />
              Archive
            </button>
          ) : null}
        </header>

        {isLoading ? (
          <div className="flex justify-center rounded-lg border border-slate-200 bg-white p-10 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : null}

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        {message ? (
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            {message}
          </div>
        ) : null}

        {node ? (
          <section className="rounded-lg border border-slate-200 bg-white p-6">
            <NodeForm initial={node} submitLabel="Save changes" onSubmit={handleSubmit} />
          </section>
        ) : null}
      </div>

      {showArchiveConfirm ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold tracking-normal">Archive this node?</h2>
                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Archived nodes are hidden from matching but remain available to historical applications.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close"
                onClick={() => setShowArchiveConfirm(false)}
                className="rounded p-1 text-slate-500 hover:bg-slate-100"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowArchiveConfirm(false)}
                className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleArchive()}
                disabled={isArchiving}
                className="inline-flex items-center gap-2 rounded-lg bg-red-700 px-3 py-2 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-60"
              >
                <Trash2 className="h-4 w-4" />
                {isArchiving ? "Archiving..." : "Archive node"}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </main>
  )
}
