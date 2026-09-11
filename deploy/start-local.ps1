# Start the telemetry receiver on THIS Windows machine (no Docker required).
#
# The engine is stdlib-only, so a plain Python 3.12 install is all it needs.
# Config (RECEIVER_AUTH_TOKEN, OTEL_DB, RECEIVER_LOG) is read from .env by
# billing/config.py — keep values free of trailing "# ..." comments, the loader
# does not strip them.
#
# Usage (from the repo root):
#     .\deploy\start-local.ps1
#     .\deploy\start-local.ps1 -Port 4318 -BindAll
#
# Runs in the foreground; Ctrl+C stops it and closes the store cleanly.

param(
    [string] $BindHost = '127.0.0.1',
    [int]    $Port     = 4318,
    # Bind 0.0.0.0 to accept telemetry from other machines. Only do this behind
    # a TLS reverse proxy — see the Caddy sidecar note in docker-compose.yml.
    [switch] $BindAll,
    # Accept unauthenticated writes, even though .env sets RECEIVER_AUTH_TOKEN.
    # This passes --open, which clears the token for the run. Merely omitting
    # --require-auth does NOT open the receiver: that flag only decides whether
    # it refuses to START without a token, so with a token in .env the receiver
    # would have gone on 401-ing every write while this script said "OPEN".
    [switch] $Open
)

$ErrorActionPreference = 'Stop'

# Run from the repo root regardless of where this was invoked.
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $python)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    # The Microsoft Store alias stubs live under WindowsApps and are not a real
    # interpreter — reject them so the failure is legible.
    if ($cmd -and $cmd.Source -notlike '*\WindowsApps\*') {
        $python = $cmd.Source
    } else {
        throw "Python 3.12 not found. Install it with: winget install --id Python.Python.3.12 --scope user"
    }
}

if (-not (Test-Path '.\.env')) {
    throw "No .env found. Copy .env.example to .env and set RECEIVER_AUTH_TOKEN."
}
if (-not (Test-Path '.\data')) {
    New-Item -ItemType Directory '.\data' | Out-Null
}

if ($BindAll) { $BindHost = '0.0.0.0' }

$callArgs = @('-u', '-m', 'billing.otel.receiver', '--host', $BindHost, '--port', $Port)
if ($Open) { $callArgs += '--open' } else { $callArgs += '--require-auth' }

# Both branches are load-bearing for this line being true: --open really clears
# the token, and --require-auth makes the receiver refuse to start without one.
# So whichever is printed here matches the receiver's own auth= banner — if the
# two ever disagree, one of those flags has stopped doing its job.
$mode = if ($Open) { 'OPEN — no token required, any writer accepted' }
        else       { 'auth required — RECEIVER_AUTH_TOKEN must be set' }
Write-Host "Starting receiver on http://${BindHost}:${Port}  [$mode]"
Write-Host "Store: $repo\data\otel.db   Log: $repo\data\receiver.log"
Write-Host "Ctrl+C to stop."

# -u keeps the receiver's stdout unbuffered so the startup banner and per-request
# lines appear immediately (the Dockerfile gets this via PYTHONUNBUFFERED).
& $python @callArgs
