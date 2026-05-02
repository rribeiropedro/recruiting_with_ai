"use client"

import { CheckCircle2, FileText, Layers, Rows3 } from "lucide-react"
import type { ResumeTemplate } from "@/lib/generate/api"

const templates: Array<{
  id: ResumeTemplate
  label: string
  description: string
  Icon: typeof FileText
}> = [
  {
    id: "modern",
    label: "Modern",
    description: "Balanced spacing with a strong skills section.",
    Icon: FileText,
  },
  {
    id: "classic",
    label: "Classic",
    description: "Traditional resume structure for conservative teams.",
    Icon: Rows3,
  },
  {
    id: "minimal",
    label: "Minimal",
    description: "Compact single-column layout for dense experience.",
    Icon: Layers,
  },
]

function TemplatePreview({ template }: { template: ResumeTemplate }) {
  const lineWidths =
    template === "minimal"
      ? ["w-11/12", "w-10/12", "w-9/12", "w-10/12"]
      : template === "classic"
        ? ["w-10/12", "w-8/12", "w-11/12", "w-9/12"]
        : ["w-8/12", "w-11/12", "w-9/12", "w-10/12"]

  return (
    <div className="h-28 rounded-md border border-slate-200 bg-slate-50 p-3">
      <div className="h-3 w-2/3 rounded-sm bg-slate-900" />
      <div className="mt-2 h-2 w-1/2 rounded-sm bg-slate-300" />
      <div className="mt-4 space-y-2">
        {lineWidths.map((width, index) => (
          <div key={`${template}-${index}`} className={`h-2 rounded-sm bg-slate-300 ${width}`} />
        ))}
      </div>
      <div className="mt-4 grid grid-cols-3 gap-1.5">
        <div className="h-2 rounded-sm bg-emerald-200" />
        <div className="h-2 rounded-sm bg-emerald-200" />
        <div className="h-2 rounded-sm bg-emerald-200" />
      </div>
    </div>
  )
}

export function TemplatePicker({
  disabled = false,
  onChange,
  selected,
}: {
  disabled?: boolean
  onChange: (template: ResumeTemplate) => void
  selected: ResumeTemplate
}) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {templates.map(({ Icon, description, id, label }) => {
        const isSelected = selected === id
        return (
          <button
            key={id}
            type="button"
            disabled={disabled}
            onClick={() => onChange(id)}
            className={`rounded-lg border bg-white p-4 text-left transition disabled:cursor-not-allowed disabled:opacity-60 ${
              isSelected ? "border-slate-950 ring-2 ring-slate-950/10" : "border-slate-200 hover:border-slate-400"
            }`}
          >
            <TemplatePreview template={id} />
            <div className="mt-4 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Icon className="h-4 w-4 text-slate-500" />
                  <span className="text-sm font-semibold text-slate-950">{label}</span>
                </div>
                <p className="mt-1 text-sm leading-5 text-slate-600">{description}</p>
              </div>
              {isSelected ? <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" /> : null}
            </div>
          </button>
        )
      })}
    </div>
  )
}
