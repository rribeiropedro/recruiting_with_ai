import { NextRequest, NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl
  const code = searchParams.get("code") ?? ""
  const state = searchParams.get("state") ?? ""

  const backendUrl = `${BACKEND}/user/oauth/gmail/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`
  const res = await fetch(backendUrl, { redirect: "manual" })

  const location = res.headers.get("location")
  if (location) return NextResponse.redirect(new URL(location, req.url))
  return NextResponse.redirect(new URL("/settings/connections?oauth=error", req.url))
}
