"use client"

import { FormEvent, useEffect, useMemo, useState } from "react"
import { Plus, Save, Trash2, X } from "lucide-react"
import { NODE_TYPES, NodePayload, NodeResponse } from "@/lib/vault/api"

interface NodeFormProps {
  initial?: Partial<NodeResponse>
  submitLabel: string
  onSubmit: (payload: NodePayload) => Promise<void>
  showGranularityHelp?: boolean
}

const emptyPayload: NodePayload = {
  title: "",
  organization: null,
  role: null,
  start_date: null,
  end_date: null,
  description: "",
  bullet_points: [""],
  node_type: "project",
}

function dateInputValue(value: string | null | undefined) {
  return value ? value.slice(0, 10) : ""
}

function optionalText(value: string) {
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

export function NodeForm({
  initial,
  submitLabel,
  onSubmit,
  showGranularityHelp = false,
}: NodeFormProps) {
  const initialPayload = useMemo<NodePayload>(
    () => ({
      ...emptyPayload,
      ...initial,
      start_date: dateInputValue(initial?.start_date),
      end_date: dateInputValue(initial?.end_date),
      bullet_points: initial?.bullet_points?.length ? initial.bullet_points : [""],
    }),
    [initial]
  )
  const [form, setForm] = useState<NodePayload>(initialPayload)
  const [ongoing, setOngoing] = useState(!initial?.end_date && Boolean(initial?.start_date))
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [showHelp, setShowHelp] = useState(showGranularityHelp)

  useEffect(() => {
    setForm(initialPayload)
    setOngoing(!initial?.end_date && Boolean(initial?.start_date))
  }, [initialPayload, initial?.end_date, initial?.start_date])

  function setField<K extends keyof NodePayload>(field: K, value: NodePayload[K]) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  function addBullet() {
    if (form.bullet_points.length >= 10) return
    setField("bullet_points", [...form.bullet_points, ""])
  }

  function removeBullet(index: number) {
    const next = form.bullet_points.filter((_, itemIndex) => itemIndex !== index)
    setField("bullet_points", next.length ? next : [""])
  }

  function updateBullet(index: number, value: string) {
    setField(
      "bullet_points",
      form.bullet_points.map((bullet, itemIndex) => (itemIndex === index ? value : bullet))
    )
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)

    const payload: NodePayload = {
      ...form,
      title: form.title.trim(),
      organization: optionalText(form.organization ?? ""),
      role: optionalText(form.role ?? ""),
      start_date: form.start_date || null,
      end_date: ongoing ? null : form.end_date || null,
      description: form.description.trim(),
      bullet_points: form.bullet_points.map((bullet) => bullet.trim()).filter(Boolean),
    }

    if (!payload.title) {
      setError("Title is required.")
      return
    }
    if (payload.description.length < 10) {
      setError("Description must be at least 10 characters.")
      return
    }

    setIsSubmitting(true)
    try {
      await onSubmit(payload)
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Could not save this node.")
      setIsSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {showHelp ? (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
          <div className="flex items-start justify-between gap-4">
            <p>
              One node = one distinct thing you built or did. If a job had three projects,
              create three nodes; we pick the most relevant ones for each application.
            </p>
            <button
              type="button"
              aria-label="Dismiss"
              onClick={() => setShowHelp(false)}
              className="rounded p-1 text-amber-900 hover:bg-amber-100"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      ) : null}

      {error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      ) : null}

      <div className="grid gap-5 md:grid-cols-2">
        <label className="space-y-2 md:col-span-2">
          <span className="text-sm font-medium text-slate-900">Title</span>
          <input
            value={form.title}
            onChange={(event) => setField("title", event.target.value)}
            placeholder='e.g. "Real-Time Analytics Dashboard"'
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
          <span className="block text-xs text-slate-500">
            Name the specific project or experience, not your job title.
          </span>
        </label>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-900">Organization</span>
          <input
            value={form.organization ?? ""}
            onChange={(event) => setField("organization", event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
        </label>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-900">Role</span>
          <input
            value={form.role ?? ""}
            onChange={(event) => setField("role", event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
        </label>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-900">Start date</span>
          <input
            type="date"
            value={form.start_date ?? ""}
            onChange={(event) => setField("start_date", event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
          />
        </label>

        <div className="space-y-2">
          <label className="text-sm font-medium text-slate-900" htmlFor="end-date">
            End date
          </label>
          <input
            id="end-date"
            type="date"
            value={form.end_date ?? ""}
            disabled={ongoing}
            onChange={(event) => setField("end_date", event.target.value)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900 disabled:bg-slate-100"
          />
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={ongoing}
              onChange={(event) => setOngoing(event.target.checked)}
              className="h-4 w-4 rounded border-slate-300"
            />
            Ongoing
          </label>
        </div>

        <label className="space-y-2">
          <span className="text-sm font-medium text-slate-900">Type</span>
          <select
            value={form.node_type}
            onChange={(event) => setField("node_type", event.target.value as NodePayload["node_type"])}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm capitalize outline-none focus:border-slate-900"
          >
            {NODE_TYPES.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      </div>

      <label className="block space-y-2">
        <span className="text-sm font-medium text-slate-900">Description</span>
        <textarea
          value={form.description}
          onChange={(event) => setField("description", event.target.value)}
          rows={5}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
        />
        <span className="block text-xs text-slate-500">
          Describe this specific project or role: what you built, why it mattered.
        </span>
      </label>

      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium text-slate-900">Bullet points</span>
          <button
            type="button"
            onClick={addBullet}
            disabled={form.bullet_points.length >= 10}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Plus className="h-4 w-4" />
            Add bullet
          </button>
        </div>
        {form.bullet_points.map((bullet, index) => (
          <div key={index} className="flex gap-2">
            <input
              value={bullet}
              onChange={(event) => updateBullet(index, event.target.value)}
              className="min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
            />
            <button
              type="button"
              aria-label="Remove bullet"
              onClick={() => removeBullet(index)}
              className="rounded-lg border border-slate-300 p-2 text-slate-600 hover:bg-slate-50"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>

      <div className="flex justify-end">
        <button
          type="submit"
          disabled={isSubmitting}
          className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Save className="h-4 w-4" />
          {isSubmitting ? "Saving..." : submitLabel}
        </button>
      </div>
    </form>
  )
}
