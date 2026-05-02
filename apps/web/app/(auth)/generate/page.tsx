import { JobInput } from "@/components/generate/JobInput"

export default function GeneratePage() {
  return (
    <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-950 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-4xl space-y-6">
        <header>
          <h1 className="text-3xl font-semibold tracking-normal">Generate</h1>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            Start by analyzing the target role.
          </p>
        </header>

        <JobInput />
      </div>
    </main>
  )
}
