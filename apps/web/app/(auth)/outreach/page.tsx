"use client"

import { useCallback, useEffect, useState } from "react"
import { createClient } from "@/lib/supabase/client"
import { useOutreachStore } from "@/lib/stores/outreachStore"
import type {
  CampaignResponse,
  CampaignStatus,
  RealtimeCampaignPayload,
} from "@/lib/stores/outreachStore"
import { KanbanBoard } from "@/components/crm/KanbanBoard"
import { CampaignDetail } from "@/components/crm/CampaignDetail"
import Link from "next/link"

export default function OutreachPage() {
  const { campaigns, counts, isLoading, fetchCampaigns, updateStatus, handleRealtimeUpdate } =
    useOutreachStore()
  const [selected, setSelected] = useState<CampaignResponse | null>(null)
  const [gmailConnected, setGmailConnected] = useState(false)

  const fetchOAuthStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/oauth/status")
      if (res.ok) {
        const data = await res.json()
        setGmailConnected(data.gmail_connected)
      }
    } catch {}
  }, [])

  const initiateGmailOAuth = useCallback(async (returnTo?: string) => {
    try {
      const res = await fetch("/api/oauth/gmail/initiate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ return_to: returnTo }),
      })
      const { auth_url } = await res.json()
      window.location.href = auth_url
    } catch {}
  }, [])

  useEffect(() => {
    fetchCampaigns()
    fetchOAuthStatus()
  }, [fetchCampaigns, fetchOAuthStatus])

  // Supabase Realtime subscription
  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (!user) return
      supabase
        .channel("campaigns")
        .on(
          "postgres_changes",
          {
            event: "*",
            schema: "public",
            table: "outreach_campaigns",
            filter: `user_id=eq.${user.id}`,
          },
          (payload) => {
            handleRealtimeUpdate({
              eventType: payload.eventType,
              new: payload.new as RealtimeCampaignPayload["new"],
              old: payload.old as RealtimeCampaignPayload["old"],
            })
          }
        )
        .subscribe()
    })
  }, [handleRealtimeUpdate])

  if (isLoading && campaigns.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-400">
        Loading campaigns…
      </div>
    )
  }

  if (campaigns.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-4 text-center">
        <p className="text-gray-500 text-sm">No outreach campaigns yet.</p>
        <p className="text-gray-400 text-xs max-w-xs">
          Generate a resume for a job, then click &quot;Send to Hiring Manager&quot; to start your first campaign.
        </p>
        <Link
          href="/generate"
          className="text-sm bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700"
        >
          → Generate a resume
        </Link>
      </div>
    )
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Outreach CRM</h1>
        {!gmailConnected && (
          <button
            className="text-sm text-blue-600 border border-blue-300 px-3 py-1.5 rounded-lg hover:bg-blue-50"
            onClick={() => initiateGmailOAuth()}
          >
            Connect Gmail
          </button>
        )}
      </div>

      <KanbanBoard
        campaigns={campaigns}
        counts={counts}
        onStatusChange={(id, status) => updateStatus(id, status as CampaignStatus)}
        onExpand={setSelected}
      />

      {selected && (
        <CampaignDetail
          campaign={selected}
          onClose={() => setSelected(null)}
          gmailConnected={gmailConnected}
          onConnectGmail={() => initiateGmailOAuth(`/outreach`)}
        />
      )}
    </div>
  )
}
