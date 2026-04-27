"use client"

import { useState } from "react"
import {
  DndContext,
  DragEndEvent,
  DragOverlay,
  DragStartEvent,
  PointerSensor,
  useSensor,
  useSensors,
  closestCenter,
} from "@dnd-kit/core"
import {
  SortableContext,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable"
import { CampaignCard } from "./CampaignCard"
import type { CampaignResponse, CampaignStatus } from "@/lib/stores/outreachStore"
import {
  STATUS_LABELS,
  VALID_TRANSITIONS,
  KANBAN_COLUMNS,
  COLLAPSED_COLUMNS,
} from "@/lib/stores/outreachStore"

interface Props {
  campaigns: CampaignResponse[]
  counts: Record<string, number>
  onStatusChange: (id: string, status: CampaignStatus) => void
  onExpand: (campaign: CampaignResponse) => void
}

interface ColumnProps {
  status: CampaignStatus
  campaigns: CampaignResponse[]
  count: number
  isInvalid: boolean
  onExpand: (c: CampaignResponse) => void
}

function KanbanColumn({ status, campaigns, count, isInvalid, onExpand }: ColumnProps) {
  return (
    <div
      className={`flex flex-col gap-2 min-w-[220px] w-56 transition-opacity ${isInvalid ? "opacity-40" : ""}`}
    >
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-semibold text-sm text-gray-700">
          {STATUS_LABELS[status]}
        </h3>
        <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded-full">{count}</span>
      </div>

      <SortableContext items={campaigns.map((c) => c.id)} strategy={verticalListSortingStrategy}>
        <div
          id={status}
          className={`flex flex-col gap-2 min-h-[120px] rounded-lg p-2 transition-colors ${
            isInvalid ? "bg-gray-50 border-2 border-dashed border-gray-200" : "bg-gray-50 border-2 border-dashed border-transparent"
          }`}
        >
          {campaigns.length === 0 ? (
            <div className="h-16 flex items-center justify-center rounded-md border-2 border-dashed border-gray-200">
              <span className="text-xs text-gray-400">Drop here</span>
            </div>
          ) : (
            campaigns.map((c) => (
              <CampaignCard key={c.id} campaign={c} onExpand={onExpand} />
            ))
          )}
        </div>
      </SortableContext>
    </div>
  )
}

export function KanbanBoard({ campaigns, counts, onStatusChange, onExpand }: Props) {
  const [activeCampaign, setActiveCampaign] = useState<CampaignResponse | null>(null)
  const [invalidColumns, setInvalidColumns] = useState<CampaignStatus[]>([])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } })
  )

  function campaignsForStatus(status: CampaignStatus) {
    return campaigns.filter((c) => c.status === status)
  }

  function handleDragStart(event: DragStartEvent) {
    const campaign = campaigns.find((c) => c.id === event.active.id)
    if (!campaign) return
    setActiveCampaign(campaign)
    const invalid = ([...KANBAN_COLUMNS, ...COLLAPSED_COLUMNS] as CampaignStatus[]).filter(
      (s) => !VALID_TRANSITIONS[campaign.status]?.includes(s)
    )
    setInvalidColumns(invalid)
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveCampaign(null)
    setInvalidColumns([])

    const { active, over } = event
    if (!over) return

    const campaign = campaigns.find((c) => c.id === active.id)
    if (!campaign) return

    // over.id can be a column status string or another campaign id
    // Determine target column: if over.id is a campaign, get its status
    let targetStatus = over.id as CampaignStatus
    const overCampaign = campaigns.find((c) => c.id === over.id)
    if (overCampaign) targetStatus = overCampaign.status

    if (targetStatus === campaign.status) return
    if (!VALID_TRANSITIONS[campaign.status]?.includes(targetStatus)) return

    onStatusChange(campaign.id, targetStatus)
  }

  const [showCollapsed, setShowCollapsed] = useState(false)

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex gap-4 overflow-x-auto pb-4">
        {KANBAN_COLUMNS.map((status) => (
          <KanbanColumn
            key={status}
            status={status}
            campaigns={campaignsForStatus(status)}
            count={counts[status] ?? 0}
            isInvalid={invalidColumns.includes(status)}
            onExpand={onExpand}
          />
        ))}

        <div className="flex flex-col gap-2 min-w-[180px]">
          <button
            className="text-xs text-gray-500 hover:text-gray-700 text-left px-1"
            onClick={() => setShowCollapsed((v) => !v)}
          >
            {showCollapsed ? "▼" : "▶"} Rejected / Archived
          </button>
          {showCollapsed &&
            COLLAPSED_COLUMNS.map((status) => (
              <KanbanColumn
                key={status}
                status={status}
                campaigns={campaignsForStatus(status)}
                count={counts[status] ?? 0}
                isInvalid={invalidColumns.includes(status)}
                onExpand={onExpand}
              />
            ))}
        </div>
      </div>

      <DragOverlay>
        {activeCampaign && (
          <CampaignCard campaign={activeCampaign} isOverlay onExpand={() => {}} />
        )}
      </DragOverlay>
    </DndContext>
  )
}
