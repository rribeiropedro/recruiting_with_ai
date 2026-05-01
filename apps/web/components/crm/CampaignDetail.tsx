"use client"

import { useState } from "react"
import type { CampaignResponse } from "@/lib/stores/outreachStore"
import { useOutreachStore } from "@/lib/stores/outreachStore"

interface Props {
  campaign: CampaignResponse
  onClose: () => void
  gmailConnected: boolean
  onConnectGmail: () => void
}

const SEND_ERROR_MESSAGES: Record<string, { text: string; actionLabel?: string }> = {
  token_expired: {
    text: "Your Gmail connection expired.",
    actionLabel: "Reconnect Gmail",
  },
  rate_limited: {
    text: "Gmail is rate-limiting sends. Wait a few minutes and try again.",
  },
}

function getSendErrorMessage(error: string | null) {
  if (!error) return null
  if (error in SEND_ERROR_MESSAGES) return SEND_ERROR_MESSAGES[error]
  return { text: "Send failed. Check your connection and try again." }
}

export function CampaignDetail({ campaign, onClose, gmailConnected, onConnectGmail }: Props) {
  const { draftEmail, sendEmail, updateCampaign } = useOutreachStore()
  const [drafting, setDrafting] = useState(false)
  const [sending, setSending] = useState(false)
  const [editingEmail, setEditingEmail] = useState(false)
  const [emailBody, setEmailBody] = useState(campaign.email_body ?? "")
  const [emailSubject, setEmailSubject] = useState(campaign.email_subject ?? "")
  const [notes, setNotes] = useState(campaign.notes ?? "")
  const [tone, setTone] = useState<"conversational" | "professional" | "bold">("conversational")
  const [sendError, setSendError] = useState(campaign.send_error)

  const canSend =
    campaign.status === "drafted" && !!campaign.contact_email && !!campaign.email_body

  async function handleDraft() {
    setDrafting(true)
    try {
      const result = await draftEmail(campaign.id, tone)
      setEmailSubject(result.email_subject)
      setEmailBody(result.email_body)
    } finally {
      setDrafting(false)
    }
  }

  async function handleSend() {
    if (!gmailConnected) {
      onConnectGmail()
      return
    }
    setSending(true)
    setSendError(null)
    try {
      const result = await sendEmail(campaign.id, "gmail")
      if (!result.success) setSendError(result.error)
    } finally {
      setSending(false)
    }
  }

  async function handleSaveEmail() {
    await updateCampaign(campaign.id, { email_subject: emailSubject, email_body: emailBody })
    setEditingEmail(false)
  }

  async function handleBlurNotes() {
    if (notes !== campaign.notes) {
      await updateCampaign(campaign.id, { notes })
    }
  }

  const errorInfo = getSendErrorMessage(sendError ?? null)

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-end z-50" onClick={onClose}>
      <div
        className="bg-white h-full w-full max-w-2xl overflow-y-auto p-6 flex flex-col gap-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-gray-900">
              {campaign.company_name ?? "Unknown Company"}
            </h2>
            <p className="text-sm text-gray-500">{campaign.role_title ?? "—"}</p>
          </div>
          <button className="text-gray-400 hover:text-gray-600 text-2xl" onClick={onClose}>
            ×
          </button>
        </div>

        {/* Contact */}
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Contact</h3>
          <p className="text-sm text-gray-900">{campaign.contact_name ?? "Not found"}</p>
          {campaign.contact_title && <p className="text-sm text-gray-500">{campaign.contact_title}</p>}
          {campaign.contact_email ? (
            <p className="text-sm text-blue-600">{campaign.contact_email}</p>
          ) : (
            <p className="text-xs text-amber-600 mt-1">
              Contact not found — add manually below
            </p>
          )}
        </section>

        {/* Error banner */}
        {errorInfo && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
            {errorInfo.text}
            {errorInfo.actionLabel && (
              <button className="ml-2 underline font-medium" onClick={onConnectGmail}>
                {errorInfo.actionLabel}
              </button>
            )}
          </div>
        )}

        {/* Email */}
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-semibold text-gray-700">Email</h3>
            <div className="flex gap-2">
              <select
                className="text-xs border rounded px-2 py-1 text-gray-600"
                value={tone}
                onChange={(e) => setTone(e.target.value as typeof tone)}
              >
                <option value="conversational">Conversational</option>
                <option value="professional">Professional</option>
                <option value="bold">Bold</option>
              </select>
              <button
                className="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-40"
                onClick={handleDraft}
                disabled={drafting}
              >
                {drafting ? "Drafting…" : campaign.email_body ? "Regenerate" : "Draft Email"}
              </button>
              {campaign.email_body && !editingEmail && (
                <button
                  className="text-xs text-gray-500 hover:text-gray-700"
                  onClick={() => setEditingEmail(true)}
                >
                  Edit
                </button>
              )}
              {editingEmail && (
                <button
                  className="text-xs text-green-600 hover:text-green-800"
                  onClick={handleSaveEmail}
                >
                  Save
                </button>
              )}
            </div>
          </div>

          {editingEmail ? (
            <div className="flex flex-col gap-2">
              <input
                className="border rounded px-3 py-2 text-sm w-full"
                value={emailSubject}
                onChange={(e) => setEmailSubject(e.target.value)}
                placeholder="Subject"
              />
              <textarea
                className="border rounded px-3 py-2 text-sm w-full h-48 resize-y"
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
              />
            </div>
          ) : campaign.email_body ? (
            <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-800 whitespace-pre-wrap">
              {campaign.email_subject && (
                <p className="font-semibold mb-2">Subject: {campaign.email_subject}</p>
              )}
              {campaign.email_body}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">No email drafted yet.</p>
          )}
        </section>

        {/* Send button */}
        {campaign.status !== "sent" && campaign.status !== "responded" && campaign.status !== "meeting_scheduled" && (
          <div>
            {!gmailConnected ? (
              <button
                className="w-full bg-gray-100 text-gray-700 py-2 px-4 rounded-lg text-sm font-medium hover:bg-gray-200"
                onClick={onConnectGmail}
              >
                Connect Gmail to Send
              </button>
            ) : (
              <button
                className="w-full bg-blue-600 text-white py-2 px-4 rounded-lg text-sm font-semibold hover:bg-blue-700 disabled:opacity-40"
                onClick={handleSend}
                disabled={!canSend || sending}
              >
                {sending ? "Sending…" : "Send Email"}
              </button>
            )}
          </div>
        )}

        {/* Notes */}
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Notes</h3>
          <textarea
            className="w-full border rounded px-3 py-2 text-sm h-24 resize-y text-gray-700"
            placeholder="Private notes…"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            onBlur={handleBlurNotes}
          />
        </section>

        {/* Timeline */}
        <section>
          <h3 className="text-sm font-semibold text-gray-700 mb-2">Timeline</h3>
          <ul className="text-xs text-gray-500 space-y-1">
            <li>Created: {new Date(campaign.created_at).toLocaleString()}</li>
            {campaign.email_body && <li>Drafted</li>}
            {campaign.status === "sent" && <li>Sent</li>}
            {campaign.status === "responded" && <li>Responded</li>}
            {campaign.status === "meeting_scheduled" && <li>Meeting scheduled</li>}
          </ul>
        </section>
      </div>
    </div>
  )
}
