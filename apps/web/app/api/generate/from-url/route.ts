import { NextRequest } from "next/server"
import { forwardToBackend } from "@/lib/backend/proxy"

export async function POST(request: NextRequest) {
  const body = await request.text()
  return forwardToBackend(request, "/generate/from-url", { body })
}
