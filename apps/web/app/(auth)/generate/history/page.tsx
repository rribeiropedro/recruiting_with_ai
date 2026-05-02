import { ApplicationHistory } from "@/components/generate/ApplicationHistory"

export default function GenerateHistoryPage() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-6xl space-y-6">
        <header>
          <h1 className="text-3xl font-semibold tracking-normal">Generated applications</h1>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Review generated resumes, matched experience, and PDF previews.
          </p>
        </header>

        <ApplicationHistory />
      </div>
    </main>
  )
}
