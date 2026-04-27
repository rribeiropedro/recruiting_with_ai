import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

async function getToken() {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

export async function GET(_req: NextRequest, { params }: { params: { id: string } }) {
  const token = await getToken()
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  const res = await fetch(`${BACKEND}/outreach/campaigns/${params.id}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return NextResponse.json(await res.json(), { status: res.status })
}

export async function PATCH(req: NextRequest, { params }: { params: { id: string } }) {
  const token = await getToken()
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  const body = await req.text()
  const res = await fetch(`${BACKEND}/outreach/campaigns/${params.id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
    body,
  })
  return NextResponse.json(await res.json(), { status: res.status })
}
