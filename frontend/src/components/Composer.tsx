import { useState } from "react"

interface ComposerProps {
  disabled: boolean
  onSend: (text: string) => void
}

/** Pill-shaped input: Enter sends, Shift+Enter for a newline.
 * Positioning (centered hero vs bottom bar) is the parent's job. */
function Composer({ disabled, onSend }: ComposerProps) {
  const [text, setText] = useState("")

  function submit() {
    const trimmed = text.trim()
    if (trimmed === "" || disabled) {
      return
    }
    setText("")
    onSend(trimmed)
  }

  return (
    <form
      className="flex w-full items-end gap-2 rounded-full bg-muted px-5 py-2.5 transition-shadow focus-within:ring-2 focus-within:ring-ring"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      <textarea
        autoFocus
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault()
            submit()
          }
        }}
        placeholder="Ask about the company wiki…"
        rows={1}
        className="max-h-40 flex-1 resize-none bg-transparent py-1.5 text-[15px] outline-none placeholder:text-muted-foreground"
      />
      <button
        type="submit"
        disabled={disabled || text.trim() === ""}
        aria-label="Send"
        className="rounded-full bg-primary p-2.5 text-primary-foreground transition-all enabled:hover:brightness-110 disabled:opacity-40"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M3 20v-6l8-2-8-2V4l19 8-19 8z" />
        </svg>
      </button>
    </form>
  )
}

export default Composer
