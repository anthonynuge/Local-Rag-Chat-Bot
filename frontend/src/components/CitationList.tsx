import type { Citation } from "@/api"

/** Source chips under an answer; renders nothing when the answer cites nothing. */
function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return null
  }

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {citations.map((citation) => (
        <span
          key={citation.id}
          className="rounded-full border border-border bg-muted px-3 py-1 text-[13px] font-medium text-muted-foreground"
        >
          [{citation.id}] {citation.source}
          {citation.heading !== "" && ` — ${citation.heading}`}
        </span>
      ))}
    </div>
  )
}

export default CitationList
