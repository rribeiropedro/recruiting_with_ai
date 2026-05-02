import { NextRequest } from "next/server"
import { forwardToBackend } from "@/lib/backend/proxy"

export async function POST(request: NextRequest, { params }: { params: { id: string } }) {
  return forwardToBackend(request, `/generate/application/${encodeURIComponent(params.id)}/regenerate`, {
    method: "POST",
  })
}
