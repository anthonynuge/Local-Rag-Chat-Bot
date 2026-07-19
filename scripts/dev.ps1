# Start backend (:8000) and frontend (:5173) in one terminal; Ctrl+C stops both.
# Run from anywhere:   .\scripts\dev.ps1
$root = Split-Path $PSScriptRoot -Parent

$backend = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\backend" `
    uv -ArgumentList "run", "uvicorn", "main:app", "--reload"
try {
    Set-Location "$root\frontend"
    npm run dev
}
finally {
    # /T kills the whole tree: uvicorn's --reload watcher spawns a child
    # server that would otherwise survive and keep port 8000.
    if (-not $backend.HasExited) {
        taskkill /PID $backend.Id /T /F | Out-Null
    }
}
