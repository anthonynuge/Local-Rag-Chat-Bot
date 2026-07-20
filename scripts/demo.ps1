# Demo-day startup: backend (:8000) in a visible terminal beside the frontend
# (:5173), so the audience sees the per-turn pipeline trace (retrieved chunks,
# scores, packed/dropped, budget) live while you chat in the UI.
# Inside WezTerm the backend opens as a new tab of the current window,
# elsewhere as its own console window. Ctrl+C stops both.
# Run from anywhere:   .\scripts\demo.ps1
$root = Split-Path $PSScriptRoot -Parent

if ($env:WEZTERM_PANE) {
    # spawn prints the new tab's pane id; keep it so we can close the tab on exit
    $backendPane = wezterm cli spawn --cwd "$root\backend" `
        -- uv run uvicorn main:app --reload
} else {
    $backend = Start-Process -PassThru -WorkingDirectory "$root\backend" `
        uv -ArgumentList "run", "uvicorn", "main:app", "--reload"
}
try {
    Set-Location "$root\frontend"
    npm run dev
}
finally {
    if ($backendPane) {
        wezterm cli kill-pane --pane-id $backendPane
    }
    elseif (-not $backend.HasExited) {
        # /T kills the whole tree: uvicorn's --reload watcher spawns a child
        # server that would otherwise survive and keep port 8000.
        taskkill /PID $backend.Id /T /F | Out-Null
    }
}
