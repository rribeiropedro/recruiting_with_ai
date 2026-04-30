"use client"

import Link from "next/link"
import { useEffect } from "react"
import { Loader2, Plus, Search, Upload } from "lucide-react"
import { createClient } from "@/lib/supabase/client"
import { useVaultStore } from "@/lib/stores/vaultStore"
import { NODE_TYPES, NodeResponse } from "@/lib/vault/api"

function formatDate(value: string | null) {
  if (!value) return null
  return new Intl.DateTimeFormat("en", { month: "short", year: "numeric" }).format(new Date(value))
}

function dateRange(node: NodeResponse) {
  const start = formatDate(node.start_date)
  const end = node.end_date ? formatDate(node.end_date) : "Present"
  if (!start && !node.end_date) return "No dates"
  if (!start) return end
  return `${start} - ${end}`
}

function typeLabel(type: string) {
  return type.replace("_", " ")
}

function isRecentlyProcessing(node: NodeResponse) {
  if (node.is_embedded) return false
  return Date.now() - new Date(node.created_at).getTime() < 30_000
}

export default function VaultPage() {
  const nodes = useVaultStore((state) => state.nodes)
  const isLoading = useVaultStore((state) => state.isLoading)
  const error = useVaultStore((state) => state.error)
  const filter = useVaultStore((state) => state.filter)
  const hasMore = useVaultStore((state) => state.hasMore)
  const fetchNodes = useVaultStore((state) => state.fetchNodes)
  const loadMore = useVaultStore((state) => state.loadMore)
  const setFilter = useVaultStore((state) => state.setFilter)
  const updateNodeLocally = useVaultStore((state) => state.updateNodeLocally)

  useEffect(() => {
    void fetchNodes()
  }, [fetchNodes, filter.type, filter.search])

  useEffect(() => {
    const supabase = createClient()
    let active = true
    let channel: ReturnType<typeof supabase.channel> | null = null

    supabase.auth.getUser().then(({ data }) => {
      if (!active || !data.user) return
      channel = supabase
        .channel("vault-nodes")
        .on(
          "postgres_changes",
          {
            event: "UPDATE",
            schema: "public",
            table: "experience_nodes",
            filter: `user_id=eq.${data.user.id}`,
          },
          (payload) => {
            const row = payload.new as Partial<NodeResponse> & { id: string; embedding?: unknown }
            updateNodeLocally({ ...row, is_embedded: Boolean(row.embedding) })
          }
        )
        .subscribe()
    })

    return () => {
      active = false
      if (channel) void supabase.removeChannel(channel)
    }
  }, [updateNodeLocally])

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-3xl font-semibold tracking-normal">Experience Vault</h1>
            <p className="mt-1 text-sm text-slate-600">
              Manage the project, role, education, and achievement nodes used for matching.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/vault/import"
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100"
            >
              <Upload className="h-4 w-4" />
              Import Resume
            </Link>
            <Link
              href="/vault/new"
              className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-3 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              <Plus className="h-4 w-4" />
              Add Node
            </Link>
          </div>
        </header>

        <section className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 sm:flex-row">
          <label className="relative flex-1">
            <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              value={filter.search}
              onChange={(event) => setFilter({ search: event.target.value })}
              placeholder="Search title, description, or tags"
              className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-900"
            />
          </label>
          <select
            value={filter.type ?? ""}
            onChange={(event) => setFilter({ type: event.target.value || null })}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm capitalize outline-none focus:border-slate-900"
          >
            <option value="">All types</option>
            {NODE_TYPES.map((type) => (
              <option key={type} value={type}>
                {typeLabel(type)}
              </option>
            ))}
          </select>
        </section>

        {error ? (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        {!isLoading && nodes.length === 0 ? (
          <section className="rounded-lg border border-slate-200 bg-white px-6 py-14 text-center">
            <h2 className="text-2xl font-semibold tracking-normal">Your Vault is empty</h2>
            <p className="mx-auto mt-3 max-w-2xl text-sm leading-6 text-slate-600">
              Instead of one static resume, your Vault stores each project, role, and achievement
              separately. For every job you apply to, we pick the 5 most relevant pieces and tailor
              them to that job&apos;s language.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-3">
              <Link
                href="/vault/new"
                className="inline-flex items-center gap-2 rounded-lg bg-slate-950 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
              >
                <Plus className="h-4 w-4" />
                Add your first experience
              </Link>
              <Link
                href="/vault/import"
                className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100"
              >
                <Upload className="h-4 w-4" />
                Import from resume PDF
              </Link>
            </div>
          </section>
        ) : (
          <section className="grid gap-4 md:grid-cols-2">
            {nodes.map((node) => (
              <Link
                href={`/vault/${node.id}`}
                key={node.id}
                className="block rounded-lg border border-slate-200 bg-white p-5 hover:border-slate-400"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h2 className="truncate text-lg font-semibold tracking-normal">{node.title}</h2>
                    <p className="mt-1 text-sm text-slate-600">
                      {[node.organization, node.role].filter(Boolean).join(" - ") || "Independent"}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {isRecentlyProcessing(node) ? (
                      <span title="Processing" className="rounded-full p-1 text-slate-500">
                        <Loader2 className="h-4 w-4 animate-spin" />
                      </span>
                    ) : null}
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium capitalize text-slate-700">
                      {typeLabel(node.node_type)}
                    </span>
                  </div>
                </div>

                <p className="mt-3 line-clamp-3 text-sm leading-6 text-slate-700">{node.description}</p>
                <div className="mt-4 text-xs text-slate-500">{dateRange(node)}</div>
                {node.tags.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {node.tags.slice(0, 8).map((tag) => (
                      <span key={tag} className="rounded-full bg-emerald-50 px-2 py-1 text-xs text-emerald-800">
                        {tag}
                      </span>
                    ))}
                  </div>
                ) : null}
              </Link>
            ))}
          </section>
        )}

        {isLoading ? (
          <div className="flex justify-center py-8 text-slate-500">
            <Loader2 className="h-5 w-5 animate-spin" />
          </div>
        ) : null}

        {hasMore ? (
          <div className="flex justify-center">
            <button
              type="button"
              onClick={() => void loadMore()}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-100"
            >
              Load more
            </button>
          </div>
        ) : null}
      </div>
    </main>
  )
}
