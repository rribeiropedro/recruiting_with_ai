import type { Metadata } from "next"
import "./globals.css"

export const metadata: Metadata = {
  title: "Career Engine",
  description: "Autonomous career application engine",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
