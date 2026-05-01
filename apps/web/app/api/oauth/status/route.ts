import { NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET() {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const res = await fetch(`${BACKEND}/user/oauth/status`, {
    headers: { Authorization: `Bearer ${session.access_token}` },
  })
  return NextResponse.json(await res.json(), { status: res.status })
}
