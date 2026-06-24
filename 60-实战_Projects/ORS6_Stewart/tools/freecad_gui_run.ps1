# ORS6_Stewart · FreeCAD GUI postprocess launcher
# 道法自然: GUI mode 给 5 FCStd 设颜色 + 截图 + saveAs (颜色持久化 + 视觉真相)
#
# 用法:
#     pwsh ORS6_Stewart\tools\freecad_gui_run.ps1
#
# 输出:
#     output/screenshots/ORS6_<pose>.png  (1200x900 isometric)
#     output/_freecad_gui.log
#     output/_freecad_gui_summary.json
#     output/ORS6_<pose>.FCStd            (overwritten with colors)

$ErrorActionPreference = "Stop"

$thisScript = $MyInvocation.MyCommand.Path
$tools = Split-Path -Parent $thisScript
$pkg   = Split-Path -Parent $tools
$root  = Split-Path -Parent $pkg
$ws    = Split-Path -Parent (Split-Path -Parent $root)

$stlRoot = Join-Path $ws "ORS6-VAM饮料摇匀器\SR6资料，签收后提供解压密码\SR6 完整资料进阶版本 签收后提供解压密码\STLs"
$outDir  = Join-Path $pkg "output"
$asciiBase = "C:\Temp\ORS6_FC"
$asciiPkg  = Join-Path $asciiBase "ORS6_Stewart"
$asciiScript = Join-Path $asciiPkg "tools\freecad_gui.py"

$guiCandidates = @(
    "D:\安装的软件\FreeCAD 1.0\bin\freecad.exe",
    "C:\Program Files\FreeCAD 1.0\bin\freecad.exe",
    "C:\Program Files\FreeCAD 1.1\bin\freecad.exe"
)
$gui = $guiCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $gui) {
    Write-Host "ERROR: freecad.exe (GUI) not found" -ForegroundColor Red
    exit 1
}

Write-Host "═══ ORS6 FreeCAD GUI postprocess ═══" -ForegroundColor Cyan
Write-Host "  freecad GUI: $gui"
Write-Host "  output dir : $outDir"
Write-Host "  ASCII pkg  : $asciiPkg"
Write-Host ""

# Ensure mirror exists (sync only what's needed)
Write-Host "─ mirror sync ..."
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
    exit 2
}
Copy-Item (Join-Path $pkg "_stl_bounds.json") (Join-Path $asciiPkg "_stl_bounds.json") -Force -EA 0
Write-Host "  ✓ mirror OK (rc=$rcCode)"

# Set env + launch
$env:ORS6_STL_ROOT = $stlRoot
$env:ORS6_FC_OUTPUT_DIR = $outDir

Write-Host ""
Write-Host "─ launching FreeCAD GUI (it may flash open briefly) ..."
$t0 = Get-Date
$tmpOut = Join-Path $env:TEMP "_fcgui_out.txt"
$tmpErr = Join-Path $env:TEMP "_fcgui_err.txt"

# Use Wait so we know when GUI quit. -WindowStyle Minimized to reduce desktop noise.
Start-Process -FilePath $gui -ArgumentList "`"$asciiScript`"" `
    -RedirectStandardOutput $tmpOut -RedirectStandardError $tmpErr `
    -Wait -WindowStyle Minimized

$dur = ((Get-Date) - $t0).TotalSeconds
Write-Host "  GUI duration: $([Math]::Round($dur, 2))s"

# Show log
$log = Join-Path $outDir "_freecad_gui.log"
if (Test-Path $log) {
    Write-Host ""
    Write-Host "═══ GUI log ═══" -ForegroundColor Cyan
    Get-Content $log -Encoding utf8 | ForEach-Object { "  $_" }
} else {
    Write-Host "  ✗ log not generated" -ForegroundColor Red
    Write-Host "─ stdout ─"
    if (Test-Path $tmpOut) { Get-Content $tmpOut -EA 0 | Select-Object -Last 30 }
    Write-Host "─ stderr ─"
    if (Test-Path $tmpErr) { Get-Content $tmpErr -EA 0 | Select-Object -Last 30 }
    exit 3
}

# Summary
$sum = Join-Path $outDir "_freecad_gui_summary.json"
if (Test-Path $sum) {
    $s = Get-Content $sum -Raw -Encoding utf8 | ConvertFrom-Json
    Write-Host ""
    Write-Host "═══ summary ═══" -ForegroundColor Cyan
    Write-Host "  FreeCAD:    $($s.freecad_version)"
    Write-Host "  ok:         $($s.ok_count)/$($s.total)"
    Write-Host "  duration:   $($s.duration_s)s"
    foreach ($r in $s.results) {
        $mark = if ($r.ok) { "✓" } else { "✗" }
        if ($r.ok) {
            $pngKB = [Math]::Round($r.png_size/1KB)
            Write-Host "    [$mark] $($r.pose): colored=$($r.colored)/$($r.colored + $r.skipped) · PNG=${pngKB}KB · $($r.duration_s)s"
        } else {
            Write-Host "    [$mark] $($r.pose): $($r.error)"
        }
    }
    if ($s.ok_count -eq $s.total) { exit 0 } else { exit 4 }
}
exit 0
