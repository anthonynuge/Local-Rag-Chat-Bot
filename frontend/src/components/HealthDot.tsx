import { useEffect, useState } from "react"

import { fetchHealth, type Health } from "@/api"

/** Green/red dot from GET /api/health; hover shows the failure reason. */
function HealthDot() {
  const [health, setHealth] = useState<Health | null>(null)

  useEffect(() => {
    let cancelled = false

    async function check() {
      const result = await fetchHealth()
      if (!cancelled) {
        setHealth(result)
      }
    }

    check()
    const timer = setInterval(check, 30_000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [])

  const ok = health?.status === "ok"
  const label =
    health === null ? "checking…" : ok ? "backend healthy" : (health.reason ?? "unhealthy")
  const dotColor = health === null ? "bg-muted-foreground" : ok ? "bg-success" : "bg-destructive"

  return (
    <span className="flex items-center" title={label}>
      <span className={`h-2.5 w-2.5 rounded-full ${dotColor}`} />
    </span>
  )
}

export default HealthDot
