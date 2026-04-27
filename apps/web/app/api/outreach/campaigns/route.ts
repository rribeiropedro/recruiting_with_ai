import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

async function forwardToBackend(req: NextRequest, path: string, init?: RequestInit) {
  const supabase = createClient()
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const url = new URL(path, BACKEND)
  req.nextUrl.searchParams.forEach((v, k) => url.searchParams.set(k, v))

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${session.access_token}`,
  }

  return fetch(url.toString(), { method: req.method, headers, ...init })
}

export async function GET(req: NextRequest) {
  const res = await forwardToBackend(req, "/outreach/campaigns")
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}

export async function POST(req: NextRequest) {
  const body = await req.text()
  const res = await forwardToBackend(req, "/outreach/campaigns", { body })
  const data = await res.json()
  return NextResponse.json(data, { status: res.status })
}
