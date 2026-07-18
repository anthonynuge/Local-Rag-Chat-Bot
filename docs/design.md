# Design

Light theme only. Tokens live in `frontend/src/index.css` as Tailwind `@theme`
variables (shadcn naming); components use tokens, never raw hexes.

## Tokens

```yaml
background: "#ffffff"
foreground: "#1f1f1f"
card: "#ffffff"
card-foreground: "#1f1f1f"
popover: "#ffffff"
popover-foreground: "#1f1f1f"
primary: "#0b57d0"
primary-foreground: "#ffffff"
secondary: "#e9eef6"          # user bubble
secondary-foreground: "#1f1f1f"
muted: "#f0f4f9"              # composer fill, hover states
muted-foreground: "#575b5f"
accent: "#c2e7ff"
accent-foreground: "#001d35"
destructive: "#dc2626"
success: "#146c2e"
border: "#e1e6ed"
input: "#f0f4f9"
ring: "#0b57d0"
```

## Type & shape

- System sans. `title` 18/semibold · `body` 15 · `label` 13. Nothing else.
- White canvas; blue is accent-only, never a page wash.
- Composer: pill (fully rounded), `muted` fill, no border until focus.
- User message: `secondary` bubble, radius 16px, right-aligned.
- Assistant message: **no bubble** — plain text on the canvas, left-aligned.
- 4px spacing grid. Chat column max 768px.

## Components

- `Composer` — idle · disabled while streaming; centered under the greeting on
  the empty screen, docks to the bottom once chat starts
- `MessageBubble` — user (secondary bubble) · assistant (bare) · streaming caret
- `MessageList` — renders only once messages exist
- `CitationList` — `label` chips under the answer; hidden when empty
- `HealthDot` — ok/unhealthy from `/api/health`, tooltip shows `reason`
- `error` SSE event → destructive banner, composer re-enables

## Don'ts

No dark mode. Animations are CSS-only: message entrance (fade + 8px rise),
thinking dots, streaming caret — nothing else, no animation libraries.
No component before a screen needs it.
