import { NextRequest } from "next/server"
import { forwardToBackend } from "@/lib/backend/proxy"

export async function GET(request: NextRequest) {
  return forwardToBackend(request, "/generate/applications")
}
