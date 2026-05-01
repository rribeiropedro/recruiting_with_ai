"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { ChangeEvent, DragEvent, useEffect, useState } from "react"
import { ArrowLeft, Check, Loader2, Plus, Scissors, Trash2, Upload } from "lucide-react"
import {
  commitBulkImport,
  getBulkImportPreview,
  getBulkImportStatus,
  NODE_TYPES,
  NodePayload,
  NodeType,
  startBulkImport,
  uploadResumePdf,
} from "@/lib/vault/api"
import { useVaultStore } from "@/lib/stores/vaultStore"

const MAX_FILE_SIZE = 10 * 1024 * 1024

const emptyNode: NodePayload = {
  title: "",
  organization: null,
  role: null,
  start_date: null,
  end_date: null,
  description: "",
  bullet_points: [""],
  node_type: "project",
}

function optionalText(value: string) {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function statusText(status: string | null) {
  if (!status) return "Upload resume"
  if (status === "pending") return "Queued"
  if (status === "parsing") return "Parsing resume"
  if (status === "ready_to_review") return "Ready to review"
  if (status === "committing") return "Importing nodes"
  if (status === "completed") return "Imported"
  if (status === "failed") return "Failed"
  return status
}

export default function VaultImportPage() {
  const router = useRouter()
  const fetchNodes = useVaultStore((state) => state.fetchNodes)
  const [file, setFile] = useState<File | null>(null)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [status, setStatus] = useState<string | null>(null)
  const [nodes, setNodes] = useState<NodePayload[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isCommitting, setIsCommitting] = useState(false)
  const [createdCount, setCreatedCount] = useState<number | null>(null)

  function acceptFile(nextFile: File | null) {
    setError(null)
    if (!nextFile) return
    if (nextFile.type !== "application/pdf" && !nextFile.name.toLowerCase().endsWith(".pdf")) {
      setError("Upload a PDF file.")
      return
    }
    if (nextFile.size > MAX_FILE_SIZE) {
      setError("PDF must be 10MB or smaller.")
      return
    }
    setFile(nextFile)
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptFile(event.target.files?.[0] ?? null)
  }

  function onDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault()
    acceptFile(event.dataTransfer.files?.[0] ?? null)
  }

  async function startImport() {
    if (!file) {
      setError("Choose a resume PDF first.")
      return
    }
    setIsUploading(true)
    setError(null)
    try {
      const storagePath = await uploadResumePdf(file)
      const response = await startBulkImport(storagePath)
      setTaskId(response.task_id)
      setStatus("pending")
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "Could not start import.")
    } finally {
      setIsUploading(false)
    }
  }

  useEffect(() => {
    if (!taskId || ["ready_to_review", "completed", "failed"].includes(status ?? "")) return

    let active = true
    async function poll() {
      if (!taskId) return
      try {
        const next = await getBulkImportStatus(taskId)
        if (!active) return
        setStatus(next.status)
        if (next.error_message) setError(next.error_message)
        if (next.status === "ready_to_review") {
          const preview = await getBulkImportPreview(taskId)
          if (!active) return
          setNodes(preview.nodes.length ? preview.nodes : [{ ...emptyNode }])
        }
      } catch (pollError) {
        if (active) setError(pollError instanceof Error ? pollError.message : "Could not check import status.")
      }
    }

    void poll()
    const timer = window.setInterval(() => void poll(), 3000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [taskId, status])

  function patchNode(index: number, patch: Partial<NodePayload>) {
    setNodes((current) =>
      current.map((node, itemIndex) => (itemIndex === index ? { ...node, ...patch } : node))
    )
  }

  function patchBullet(nodeIndex: number, bulletIndex: number, value: string) {
    const node = nodes[nodeIndex]
    const bullets = node.bullet_points.map((bullet, itemIndex) =>
      itemIndex === bulletIndex ? value : bullet
    )
    patchNode(nodeIndex, { bullet_points: bullets })
  }

  function addBullet(nodeIndex: number) {
    const node = nodes[nodeIndex]
    if (node.bullet_points.length >= 10) return
    patchNode(nodeIndex, { bullet_points: [...node.bullet_points, ""] })
  }

  function removeBullet(nodeIndex: number, bulletIndex: number) {
    const node = nodes[nodeIndex]
    const bullets = node.bullet_points.filter((_, itemIndex) => itemIndex !== bulletIndex)
    patchNode(nodeIndex, { bullet_points: bullets.length ? bullets : [""] })
  }

  function removeNode(index: number) {
    setNodes((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  function splitNode(index: number) {
    setNodes((current) => {
      const node = current[index]
      const midpoint = Math.ceil(node.bullet_points.length / 2)
      const first = { ...node, bullet_points: node.bullet_points.slice(0, midpoint) }
      const second = {
        ...node,
        title: `${node.title} (continued)`,
        bullet_points: node.bullet_points.slice(midpoint),
      }
      if (!second.bullet_points.length) second.bullet_points = [""]
      return [...current.slice(0, index), first, second, ...current.slice(index + 1)]
    })
  }

  async function commitImport() {
    if (!taskId) return
    setIsCommitting(true)
    setError(null)
    const payload = nodes.map((node) => ({
      ...node,
      title: node.title.trim(),
      organization: optionalText(node.organization ?? ""),
      role: optionalText(node.role ?? ""),
      start_date: node.start_date || null,
      end_date: node.end_date || null,
      description: node.description.trim(),
      bullet_points: node.bullet_points.map((bullet) => bullet.trim()).filter(Boolean),
    }))
    try {
      const result = await commitBulkImport(taskId, payload)
      setCreatedCount(result.nodes_created)
      setStatus("completed")
      await fetchNodes()
    } catch (commitError) {
      setError(commitError instanceof Error ? commitError.message : "Could not import nodes.")
    } finally {
      setIsCommitting(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        <Link href="/vault" className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-950">
          <ArrowLeft className="h-4 w-4" />
          Back to Vault
        </Link>

        <header>
          <h1 className="text-3xl font-semibold tracking-normal">Import Resume PDF</h1>
          <p className="mt-1 text-sm text-slate-600">
            Review and edit every proposed node before anything is added to the Vault.
          </p>
        </header>

        <section className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {["Upload resume", "Parsing resume", "Ready to review", "Imported"].map((step) => {
              const current = step === statusText(status)
              return (
                <span
                  key={step}
                  className={`rounded-full px-3 py-1 ${
                    current ? "bg-slate-950 text-white" : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {step}
                </span>
              )
            })}
          </div>
        </section>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        {!taskId ? (
          <section className="rounded-lg border border-slate-200 bg-white p-6">
            <label
              onDragOver={(event) => event.preventDefault()}
              onDrop={onDrop}
              className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 px-6 py-12 text-center hover:border-slate-500"
            >
              <Upload className="h-8 w-8 text-slate-400" />
              <span className="mt-3 text-sm font-medium text-slate-900">
                {file ? file.name : "Choose or drop a PDF"}
              </span>
              <span className="mt-1 text-xs text-slate-500">PDF only, 10MB max</span>
              <input type="file" accept="application/pdf,.pdf" onChange={onFileChange} className="sr-only" />
            </label>
            <div className="mt-5 flex justify-end">
              <button
                type="button"
                onClick={() => void startImport()}
                disabled={!file || isUploading}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isUploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
                {isUploading ? "Uploading..." : "Analyze resume"}
              </button>
            </div>
          </section>
        ) : null}

        {taskId && status !== "ready_to_review" && status !== "completed" && status !== "failed" ? (
          <section className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-700">
            <Loader2 className="h-5 w-5 animate-spin text-slate-500" />
            {statusText(status)}
          </section>
        ) : null}

        {status === "ready_to_review" ? (
          <section className="space-y-4">
            {nodes.map((node, index) => (
              <div key={index} className="rounded-lg border border-slate-200 bg-white p-5">
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <h2 className="text-lg font-semibold tracking-normal">Proposed node {index + 1}</h2>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => splitNode(index)}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                    >
                      <Scissors className="h-4 w-4" />
                      Split
                    </button>
                    <button
                      type="button"
                      onClick={() => removeNode(index)}
                      className="inline-flex items-center gap-2 rounded-lg border border-red-200 px-3 py-2 text-sm font-medium text-red-700 hover:bg-red-50"
                    >
                      <Trash2 className="h-4 w-4" />
                      Remove
                    </button>
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <input
                    value={node.title}
                    onChange={(event) => patchNode(index, { title: event.target.value })}
                    placeholder="Title"
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900 md:col-span-2"
                  />
                  <input
                    value={node.organization ?? ""}
                    onChange={(event) => patchNode(index, { organization: event.target.value })}
                    placeholder="Organization"
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                  <input
                    value={node.role ?? ""}
                    onChange={(event) => patchNode(index, { role: event.target.value })}
                    placeholder="Role"
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                  <input
                    type="date"
                    value={node.start_date ?? ""}
                    onChange={(event) => patchNode(index, { start_date: event.target.value })}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                  <input
                    type="date"
                    value={node.end_date ?? ""}
                    onChange={(event) => patchNode(index, { end_date: event.target.value })}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                  <select
                    value={node.node_type}
                    onChange={(event) => patchNode(index, { node_type: event.target.value as NodeType })}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm capitalize outline-none focus:border-slate-900"
                  >
                    {NODE_TYPES.map((type) => (
                      <option key={type} value={type}>
                        {type}
                      </option>
                    ))}
                  </select>
                  <textarea
                    value={node.description}
                    onChange={(event) => patchNode(index, { description: event.target.value })}
                    rows={4}
                    className="rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900 md:col-span-2"
                  />
                </div>

                <div className="mt-4 space-y-2">
                  {node.bullet_points.map((bullet, bulletIndex) => (
                    <div key={bulletIndex} className="flex gap-2">
                      <input
                        value={bullet}
                        onChange={(event) => patchBullet(index, bulletIndex, event.target.value)}
                        className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                      />
                      <button
                        type="button"
                        aria-label="Remove bullet"
                        onClick={() => removeBullet(index, bulletIndex)}
                        className="rounded-lg border border-slate-300 p-2 text-slate-600 hover:bg-slate-50"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                  <button
                    type="button"
                    onClick={() => addBullet(index)}
                    className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                  >
                    <Plus className="h-4 w-4" />
                    Add bullet
                  </button>
                </div>
              </div>
            ))}

            <div className="flex flex-wrap items-center justify-end gap-3">
              <Link href="/vault" className="text-sm font-medium text-slate-600 hover:text-slate-950">
                Cancel
              </Link>
              <button
                type="button"
                onClick={() => void commitImport()}
                disabled={isCommitting || nodes.length === 0}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isCommitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Import {nodes.length} nodes
              </button>
            </div>
          </section>
        ) : null}

        {status === "completed" ? (
          <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-6 text-emerald-950">
            <h2 className="text-lg font-semibold tracking-normal">Imported {createdCount ?? 0} nodes</h2>
            <div className="mt-4 flex gap-2">
              <button
                type="button"
                onClick={() => router.push("/vault")}
                className="rounded-lg bg-emerald-900 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800"
              >
                View Vault
              </button>
            </div>
          </section>
        ) : null}
      </div>
    </main>
  )
}
