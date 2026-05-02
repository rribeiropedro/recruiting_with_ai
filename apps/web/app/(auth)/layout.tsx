import { redirect } from "next/navigation"
import Link from "next/link"
import { BriefcaseBusiness, Database, FileText, Settings } from "lucide-react"
import { createClient } from "@/lib/supabase/server"
import { PipelineStatus } from "@/components/shared/PipelineStatus"

const navItems = [
  { href: "/vault", label: "Vault", Icon: Database },
  { href: "/generate", label: "Generate", Icon: FileText },
  { href: "/outreach", label: "Outreach", Icon: BriefcaseBusiness },
  { href: "/settings", label: "Settings", Icon: Settings },
]

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const supabase = createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect("/login")
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-950 lg:grid lg:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="hidden border-r border-slate-200 bg-white px-4 py-6 lg:flex lg:flex-col lg:gap-6">
        <Link href="/generate" className="text-base font-semibold tracking-normal text-slate-950">
          Career Engine
        </Link>
        <nav className="space-y-1">
          {navItems.map(({ Icon, href, label }) => (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 hover:text-slate-950"
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="mt-auto">
          <PipelineStatus />
        </div>
      </aside>

      <div className="border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
        <div className="flex items-center justify-between gap-3">
          <Link href="/generate" className="text-base font-semibold text-slate-950">
            Career Engine
          </Link>
          <nav className="flex items-center gap-1">
            {navItems.slice(0, 3).map(({ Icon, href, label }) => (
              <Link
                key={href}
                href={href}
                aria-label={label}
                className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-950"
              >
                <Icon className="h-4 w-4" />
              </Link>
            ))}
          </nav>
        </div>
        <div className="mt-3">
          <PipelineStatus />
        </div>
      </div>

      <div className="min-w-0">{children}</div>
    </div>
  )
}
