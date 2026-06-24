# ORS6 · 道法自然 · 一键全启
# Cascade-managed · 2026-05-09
#
# What it does:
#   1. Detect FreeCAD GUI alive + RPC port 9875 alive
#   2. Detect viewer :8871 alive
#   3. If RPC dead but FreeCAD alive: tell user to restart FreeCAD (auto-RPC will kick in on next start)
#   4. If FreeCAD not running: launch FreeCAD GUI (auto-RPC fires after ~2s)
#   5. If viewer dead: launch viewer in background
#   6. Wait for both to be alive; ping RPC; open browser
#
# Usage:
#   pwsh -File tools\dao_one_key.ps1
#   pwsh -File tools\dao_one_key.ps1 -RestartFreeCAD   # close any running FreeCAD first

[CmdletBinding()]
param(
  [switch]$RestartFreeCAD,
  [switch]$NoBrowser,
  [int]$ViewerPort = 8871,
  [int]$RpcPort = 9875
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSCommandPath)  # ORS6_Stewart/
$projects = Split-Path -Parent $root                              # 60-实战_Projects/
$py = "C:\ProgramData\anaconda3\python.exe"
$fcExe = "D:\安装的软件\FreeCAD 1.0\bin\freecad.exe"

function Test-Port {
  param([int]$Port, [string]$Addr = "127.0.0.1", [int]$TimeoutMs = 400)
  $client = New-Object System.Net.Sockets.TcpClient
  try {
    $iar = $client.BeginConnect($Addr, $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs, $false)
    if ($ok -and $client.Connected) { $client.Close(); return $true }
    $client.Close(); return $false
  } catch { return $false }
}

function Get-FreeCADPid {
  $p = Get-Process freecad -EA SilentlyContinue | Select-Object -First 1
  if ($p) { return $p.Id } else { return 0 }
}

Write-Host "═══ ORS6 · 道法自然 · 一键全启 ═══" -ForegroundColor Cyan
Write-Host ""

# ── 1. FreeCAD GUI ──
$fcPid = Get-FreeCADPid
if ($RestartFreeCAD -and $fcPid -gt 0) {
  Write-Host "[1] Stop FreeCAD PID=$fcPid (RestartFreeCAD requested)" -ForegroundColor Yellow
  Stop-Process -Id $fcPid -Force
  Start-Sleep -Milliseconds 600
  $fcPid = 0
}

if ($fcPid -eq 0) {
  if (-not (Test-Path $fcExe)) {
    Write-Error "[1] FreeCAD exe not found: $fcExe"
    exit 1
  }
  Write-Host "[1] Launch FreeCAD GUI..." -ForegroundColor Cyan
  Start-Process $fcExe
  Start-Sleep -Milliseconds 800
  $fcPid = Get-FreeCADPid
  Write-Host "    PID=$fcPid spawned"
} else {
  Write-Host "[1] FreeCAD already running PID=$fcPid" -ForegroundColor Green
}

# ── 2. wait for RPC port (auto-RPC kicks in 2s after FreeCAD GUI ready) ──
Write-Host "[2] Wait for RPC :$RpcPort..." -ForegroundColor Cyan
$rpcAlive = $false
for ($i = 0; $i -lt 30; $i++) {
  if (Test-Port -Port $RpcPort) { $rpcAlive = $true; break }
  Start-Sleep -Milliseconds 700
  Write-Host -NoNewline "."
}
Write-Host ""
if (-not $rpcAlive) {
  Write-Host "    RPC :$RpcPort still closed after ~21s" -ForegroundColor Yellow
  Write-Host "    -> If FreeCAD just opened, give it a moment then re-run." -ForegroundColor Yellow
  Write-Host "    -> If it was already running before InitGui.py was updated," -ForegroundColor Yellow
  Write-Host "       run with -RestartFreeCAD to pick up the new auto-RPC hook." -ForegroundColor Yellow
} else {
  Write-Host "    RPC :$RpcPort OPEN" -ForegroundColor Green
}

# ── 3. viewer ──
if (Test-Port -Port $ViewerPort) {
  Write-Host "[3] viewer :$ViewerPort already alive" -ForegroundColor Green
} else {
  Write-Host "[3] Launch viewer :$ViewerPort..." -ForegroundColor Cyan
  $viewerLog = "C:\Temp\_dao_viewer.log"
  Start-Process -FilePath $py -ArgumentList @("-m", "ORS6_Stewart.viewer.server", "$ViewerPort") `
    -WorkingDirectory $projects -RedirectStandardOutput $viewerLog -RedirectStandardError "$viewerLog.err" `
    -WindowStyle Hidden
  for ($i = 0; $i -lt 12; $i++) {
    if (Test-Port -Port $ViewerPort) { break }
    Start-Sleep -Milliseconds 500
  }
  if (Test-Port -Port $ViewerPort) {
    Write-Host "    viewer :$ViewerPort UP" -ForegroundColor Green
  } else {
    Write-Host "    viewer FAILED — see $viewerLog" -ForegroundColor Red
  }
}

# ── 4. ping RPC via dao_fc.py ──
Write-Host "[4] dao_fc state..." -ForegroundColor Cyan
$stateLog = "C:\Temp\_dao_fc_state.json"
& $py -m ORS6_Stewart.tools.dao_fc state > $stateLog 2>&1
if ($LASTEXITCODE -eq 0) {
  Get-Content $stateLog -Encoding utf8 | ForEach-Object { Write-Host "    $_" }
} else {
  Write-Host "    state failed (exit $LASTEXITCODE)" -ForegroundColor Yellow
  Get-Content $stateLog -Encoding utf8 -ErrorAction SilentlyContinue | Select-Object -First 4 | ForEach-Object { Write-Host "    $_" }
}

# ── 5. open browser ──
if (-not $NoBrowser) {
  $url = "http://localhost:$ViewerPort/"
  Write-Host "[5] open $url" -ForegroundColor Cyan
  Start-Process $url
}

Write-Host ""
Write-Host "═══ done · 道法自然 ═══" -ForegroundColor Cyan
