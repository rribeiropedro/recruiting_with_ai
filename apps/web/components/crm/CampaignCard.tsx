"use client"

import { useState } from "react"
import { useSortable } from "@dnd-kit/sortable"
import { CSS } from "@dnd-kit/utilities"
import type { CampaignResponse, CampaignStatus } from "@/lib/stores/outreachStore"
import { STATUS_LABELS } from "@/lib/stores/outreachStore"

interface Props {
  campaign: CampaignResponse
  isOverlay?: boolean
  onExpand: (campaign: CampaignResponse) => void
}

const STATUS_COLORS: Record<CampaignStatus, string> = {
  drafted: "bg-gray-100 text-gray-700",
  queued: "bg-blue-100 text-blue-700",
  sent: "bg-indigo-100 text-indigo-700",
  opened: "bg-purple-100 text-purple-700",
  responded: "bg-green-100 text-green-700",
  meeting_scheduled: "bg-emerald-100 text-emerald-700",
  rejected: "bg-red-100 text-red-700",
  archived: "bg-gray-100 text-gray-500",
}

const STATUS_ICONS: Record<CampaignStatus, string> = {
  drafted: "✉",
  queued: "⏳",
  sent: "✓",
  opened: "👁",
  responded: "💬",
  meeting_scheduled: "📅",
  rejected: "✗",
  archived: "📁",
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

export function CampaignCard({ campaign, isOverlay, onExpand }: Props) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: campaign.id })

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`bg-white rounded-lg border border-gray-200 p-3 shadow-sm cursor-pointer hover:shadow-md transition-shadow select-none ${isOverlay ? "shadow-xl rotate-2" : ""}`}
      onClick={() => onExpand(campaign)}
      {...attributes}
      {...listeners}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-semibold text-sm text-gray-900 truncate">
            {campaign.company_name ?? "Unknown Company"}
          </p>
          <p className="text-xs text-gray-500 truncate">{campaign.role_title ?? "—"}</p>
        </div>
        <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_COLORS[campaign.status]}`}>
          {STATUS_ICONS[campaign.status]} {STATUS_LABELS[campaign.status]}
        </span>
      </div>

      {campaign.contact_name && (
        <p className="mt-2 text-xs text-gray-600 truncate">
          {campaign.contact_name}
          {campaign.contact_title ? ` · ${campaign.contact_title}` : ""}
        </p>
      )}

      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-gray-400">{formatDate(campaign.created_at)}</span>
        {campaign.email_verified && (
          <span className="text-xs text-green-600">✓ verified</span>
        )}
      </div>
    </div>
  )
}
