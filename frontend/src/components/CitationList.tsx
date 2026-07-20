import type { Citation } from "@/api"

/** Source chips under an answer; renders nothing when the answer cites nothing. */
function CitationList({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) {
    return null
  }

  return (
    <div className="mt-3 flex flex-col gap-2">
      {citations.map((citation) => (
        <details
          key={citation.id}
          className="rounded-lg border border-border bg-muted text-[13px] text-muted-foreground"
        >
          <summary className="cursor-pointer px-3 py-1 font-medium">
            [{citation.id}] {citation.source}
            {citation.heading !== "" && ` — ${citation.heading}`}
          </summary>
          <pre className="whitespace-pre-wrap px-3 pb-2 font-sans text-[13px]">{citation.text}</pre>
        </details>
      ))}
    </div>
  )
}

export default CitationList
