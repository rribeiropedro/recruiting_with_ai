"use client"

import Link from "next/link"
import { useRouter } from "next/navigation"
import { ArrowLeft } from "lucide-react"
import { NodeForm } from "@/components/vault/NodeForm"
import { useVaultStore } from "@/lib/stores/vaultStore"
import { NodePayload } from "@/lib/vault/api"

export default function NewVaultNodePage() {
  const router = useRouter()
  const createNode = useVaultStore((state) => state.createNode)

  async function handleSubmit(payload: NodePayload) {
    await createNode(payload)
    router.push("/vault")
  }

  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-3xl space-y-6">
        <Link href="/vault" className="inline-flex items-center gap-2 text-sm font-medium text-slate-600 hover:text-slate-950">
          <ArrowLeft className="h-4 w-4" />
          Back to Vault
        </Link>
        <header>
          <h1 className="text-3xl font-semibold tracking-normal">Add Experience Node</h1>
          <p className="mt-1 text-sm text-slate-600">
            Capture one distinct project, role, education item, or achievement.
          </p>
        </header>
        <section className="rounded-lg border border-slate-200 bg-white p-6">
          <NodeForm submitLabel="Create node" onSubmit={handleSubmit} showGranularityHelp />
        </section>
      </div>
    </main>
  )
}
