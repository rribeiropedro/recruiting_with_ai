"use client"

import { useEffect, useState, useCallback } from "react"
import { useSearchParams } from "next/navigation"

interface OAuthStatus {
  gmail_connected: boolean
  outlook_connected: boolean
}

type ConnectionState = "connected" | "not_connected" | "expired"

function StatusBadge({ state }: { state: ConnectionState }) {
  const colors: Record<ConnectionState, string> = {
    connected: "bg-green-100 text-green-700",
    not_connected: "bg-gray-100 text-gray-500",
    expired: "bg-red-100 text-red-600",
  }
  const labels: Record<ConnectionState, string> = {
    connected: "Connected",
    not_connected: "Not connected",
    expired: "Expired",
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${colors[state]}`}>
      {labels[state]}
    </span>
  )
}

export default function ConnectionsPage() {
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<OAuthStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [toast, setToast] = useState<string | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/oauth/status")
      if (res.ok) setStatus(await res.json())
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const oauthResult = searchParams.get("oauth")
    if (oauthResult === "success") setToast("Account connected successfully.")
    if (oauthResult === "error") setToast("Connection failed. Please try again.")
  }, [fetchStatus, searchParams])

  async function connectGmail() {
    const res = await fetch("/api/oauth/gmail/initiate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ return_to: "/settings/connections" }),
    })
    const { auth_url } = await res.json()
    window.location.href = auth_url
  }

  async function connectOutlook() {
    const res = await fetch("/api/oauth/outlook/initiate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ return_to: "/settings/connections" }),
    })
    const { auth_url } = await res.json()
    window.location.href = auth_url
  }

  if (loading) {
    return <div className="p-6 text-gray-400 text-sm">Loading…</div>
  }

  const gmailState: ConnectionState = status?.gmail_connected ? "connected" : "not_connected"
  const outlookState: ConnectionState = status?.outlook_connected ? "connected" : "not_connected"

  return (
    <div className="p-6 max-w-xl">
      <h1 className="text-xl font-bold text-gray-900 mb-1">Email Connections</h1>
      <p className="text-sm text-gray-500 mb-6">
        Connect your inbox to send outreach emails directly from your own address.
      </p>

      {toast && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-blue-50 border border-blue-200 text-sm text-blue-700 flex items-center justify-between">
          {toast}
          <button className="ml-4 text-blue-400 hover:text-blue-600" onClick={() => setToast(null)}>
            ×
          </button>
        </div>
      )}

      <div className="flex flex-col gap-4">
        {/* Gmail */}
        <div className="border rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-red-100 rounded-full flex items-center justify-center text-sm font-bold text-red-600">
              G
            </div>
            <div>
              <p className="font-medium text-sm text-gray-900">Gmail</p>
              <StatusBadge state={gmailState} />
            </div>
          </div>
          <div className="flex gap-2">
            {gmailState === "connected" ? (
              <button className="text-xs text-gray-400 hover:text-red-500" onClick={() => {}}>
                Disconnect
              </button>
            ) : (
              <button
                className="text-sm bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700"
                onClick={connectGmail}
              >
                Connect
              </button>
            )}
          </div>
        </div>

        {/* Outlook */}
        <div className="border rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center text-sm font-bold text-blue-700">
              O
            </div>
            <div>
              <p className="font-medium text-sm text-gray-900">Outlook</p>
              <StatusBadge state={outlookState} />
            </div>
          </div>
          <div className="flex gap-2">
            {outlookState === "connected" ? (
              <button className="text-xs text-gray-400 hover:text-red-500" onClick={() => {}}>
                Disconnect
              </button>
            ) : (
              <button
                className="text-sm bg-blue-600 text-white px-4 py-1.5 rounded-lg hover:bg-blue-700"
                onClick={connectOutlook}
              >
                Connect
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
