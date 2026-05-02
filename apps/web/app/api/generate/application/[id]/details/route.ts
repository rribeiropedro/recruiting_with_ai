import { NextRequest } from "next/server"
import { forwardToBackend } from "@/lib/backend/proxy"

export async function GET(request: NextRequest, { params }: { params: { id: string } }) {
  return forwardToBackend(request, `/generate/application/${encodeURIComponent(params.id)}/details`)
}
