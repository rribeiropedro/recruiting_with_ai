import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000"

type ProxyOptions = {
  body?: BodyInit | null
  headers?: HeadersInit
  method?: string
}

async function sessionToken() {
  const supabase = createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()
  return session?.access_token ?? null
}

function responseHeaders(response: Response) {
  const headers = new Headers()
  const contentType = response.headers.get("content-type")
  if (contentType) headers.set("Content-Type", contentType)
  return headers
}

export async function forwardToBackend(
  request: NextRequest,
  path: string,
  options: ProxyOptions = {}
) {
  const token = await sessionToken()
  if (!token) return NextResponse.json({ error: "Unauthorized" }, { status: 401 })

  const url = new URL(path, BACKEND)
  request.nextUrl.searchParams.forEach((value, key) => url.searchParams.set(key, value))

  const headers = new Headers(options.headers)
  headers.set("Authorization", `Bearer ${token}`)
  if (options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(url.toString(), {
    body: options.body,
    cache: "no-store",
    headers,
    method: options.method ?? request.method,
  })

  if (response.status === 204) {
    return new NextResponse(null, { status: 204 })
  }

  const body = await response.text()
  return new NextResponse(body, {
    headers: responseHeaders(response),
    status: response.status,
  })
}
