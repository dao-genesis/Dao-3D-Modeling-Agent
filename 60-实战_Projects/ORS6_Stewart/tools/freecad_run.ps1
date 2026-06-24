# ORS6_Stewart · FreeCAD 1.0 launcher (CN-path safe)
# 道法自然: FreeCADCmd 不能 open 中文路径 .py argv, 但能加载中文路径 STL.
# 故: mirror ORS6_Stewart 到 C:\Temp\ORS6_FC\ASCII路径下, STL+output 仍指原中文位.
#
# 用法:
#     pwsh ORS6_Stewart\tools\freecad_run.ps1
#     # 或在仓库根:
#     pwsh -File "60-实战_Projects\ORS6_Stewart\tools\freecad_run.ps1"
#
# 输出: ORS6_Stewart/output/{ORS6_<pose>.FCStd, ORS6_<pose>.step,
#                            _freecad_build.log, _freecad_5pose_summary.json}

$ErrorActionPreference = "Stop"

# ── 1. Locate paths ─────────────────────────────────────────────────────────
$thisScript = $MyInvocation.MyCommand.Path
$tools  = Split-Path -Parent $thisScript                # ORS6_Stewart/tools/
$pkg    = Split-Path -Parent $tools                     # ORS6_Stewart/
$root   = Split-Path -Parent $pkg                       # 60-实战_Projects/
$ws     = Split-Path -Parent (Split-Path -Parent $root) # 一生二/

$stlRoot = Join-Path $ws "ORS6-VAM饮料摇匀器\SR6资料，签收后提供解压密码\SR6 完整资料进阶版本 签收后提供解压密码\STLs"
$outDir  = Join-Path $pkg "output"

# ASCII mirror destination
$asciiBase = "C:\Temp\ORS6_FC"
$asciiPkg  = Join-Path $asciiBase "ORS6_Stewart"
$asciiScript = Join-Path $asciiPkg "tools\freecad_build.py"

# ── 2. Locate FreeCAD ───────────────────────────────────────────────────────
$fcCandidates = @(
    "D:\安装的软件\FreeCAD 1.0\bin\FreeCADCmd.exe",
    "C:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe",
    "C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe",
    "D:\Program Files\FreeCAD 1.0\bin\FreeCADCmd.exe"
)
$fc = $fcCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $fc) {
    Write-Host "ERROR: FreeCADCmd.exe not found. Tried:" -ForegroundColor Red
    $fcCandidates | ForEach-Object { Write-Host "  $_" }
    exit 1
}

Write-Host "═══ ORS6 FreeCAD build ═══" -ForegroundColor Cyan
Write-Host "  FreeCAD:    $fc"
Write-Host "  package:    $pkg"
Write-Host "  STL root:   $stlRoot"
Write-Host "  output dir: $outDir"
Write-Host "  ASCII pkg:  $asciiPkg"
Write-Host ""

# ── 3. Sanity ────────────────────────────────────────────────────────────────
if (-not (Test-Path $stlRoot)) {
    Write-Host "ERROR: STL root not found: $stlRoot" -ForegroundColor Red
    exit 2
}
New-Item -ItemType Directory -Force -Path $outDir, $asciiPkg | Out-Null

# ── 4. Mirror package to ASCII (exclude heavy/regenerable dirs) ─────────────
Write-Host "─ mirror sync (robocopy) ..."
$rcArgs = @(
    $pkg, $asciiPkg,
    "/MIR",
    "/XD", "output", "_archive", "__pycache__", "tests", "viewer",
    "/XF", "*.log",
    "/NFL", "/NDL", "/NP", "/NJH", "/NJS"
)
& robocopy @rcArgs | Out-Null
$rcCode = $LASTEXITCODE
if ($rcCode -ge 8) {
    Write-Host "  robocopy FAIL ($rcCode)" -ForegroundColor Red
    exit 3
}
# _stl_bounds.json is excluded by *.log? no — included since it's .json. But just in case:
Copy-Item (Join-Path $pkg "_stl_bounds.json") (Join-Path $asciiPkg "_stl_bounds.json") -Force -EA 0
Write-Host "  ✓ mirror OK (rc=$rcCode)"

# ── 5. Set env + launch ─────────────────────────────────────────────────────
$env:ORS6_STL_ROOT = $stlRoot
$env:ORS6_FC_OUTPUT_DIR = $outDir

Write-Host ""
Write-Host "─ launching FreeCAD ..."
$t0 = Get-Date
$tmpOut = Join-Path $env:TEMP "_fcrun_out.txt"
$tmpErr = Join-Path $env:TEMP "_fcrun_err.txt"
Start-Process -FilePath $fc -ArgumentList "`"$asciiScript`"" `
    -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr `
    -Wait -NoNewWindow
$dur = ((Get-Date) - $t0).TotalSeconds
Write-Host "  duration: $([Math]::Round($dur,2))s"

# ── 6. Show log ──────────────────────────────────────────────────────────────
$log = Join-Path $outDir "_freecad_build.log"
if (Test-Path $log) {
    Write-Host ""
    Write-Host "═══ build log ═══" -ForegroundColor Cyan
    Get-Content $log -Encoding utf8 | ForEach-Object { "  $_" }
} else {
    Write-Host "  ✗ log not generated" -ForegroundColor Red
    Write-Host "─ stdout ─"
    if (Test-Path $tmpOut) { Get-Content $tmpOut -EA 0 | Select-Object -Last 30 }
    Write-Host "─ stderr ─"
    if (Test-Path $tmpErr) { Get-Content $tmpErr -EA 0 | Select-Object -Last 30 }
    exit 4
}

# ── 7. Show summary ─────────────────────────────────────────────────────────
$sum = Join-Path $outDir "_freecad_5pose_summary.json"
if (Test-Path $sum) {
    $s = Get-Content $sum -Raw -Encoding utf8 | ConvertFrom-Json
    Write-Host ""
    Write-Host "═══ summary ═══" -ForegroundColor Cyan
    Write-Host "  FreeCAD:    $($s.freecad_version)"
    Write-Host "  ok:         $($s.ok_count)/$($s.total)"
    Write-Host "  duration:   $($s.duration_s)s"
    foreach ($r in $s.results) {
        $mark = if ($r.ok) { "✓" } else { "✗" }
        $fcKB = [Math]::Round($r.fcstd_size/1KB)
        $stKB = [Math]::Round($r.step_size/1KB)
        Write-Host "    [$mark] $($r.label): FCStd=${fcKB}KB STEP=${stKB}KB ($($r.duration_s)s)"
    }
    if ($s.ok_count -eq $s.total) { exit 0 } else { exit 5 }
}

exit 0
