# sw2026_auto_ui.ps1 — sldIM WebView2 GUI 自动推进哨兵
# ══════════════════════════════════════════════════════════════════════
# 道法自然 · 用户无为 · 哨兵无不为
#
# 策略 (每 N 秒一轮):
#   1. 若 sldIM 进程不在    → 退出 (安装已完成/被杀)
#   2. 若 SW2026 已注册到 reg  → 退出 (主体安装完毕, 交给后续 crack/SP stage)
#   3. 若 msiexec 在跑       → 等待 (真实安装中, 不干扰)
#   4. 截图 · 计算哈希
#      a. 与上一轮哈希相同 ≥ STICKY_THRESHOLD 次 → 认为卡在某"下一步"页
#         → 点击 (970/1024, 810/840) 归一化的"下一步"按钮坐标
#      b. 哈希变了 → 重置卡顿计数
#   5. 日志 tee 到文件
#
# 用法:
#   pwsh -File sw2026_auto_ui.ps1
#   pwsh -File sw2026_auto_ui.ps1 -IntervalSec 60 -StickyThreshold 2
param(
    [int]$IntervalSec      = 45,
    [int]$StickyThreshold  = 2,
    [int]$MaxMinutes       = 90,
    [string]$LogDir        = 'e:\道\道生一\一生二\3D建模Agent\90-日志_Logs\sw2026',
    [double]$BtnXRatio     = 0.947,   # 970/1024
    [double]$BtnYRatio     = 0.964    # 810/840
)

Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public class AU {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
    [DllImport("user32.dll")] public static extern void mouse_event(uint dwFlags, int dx, int dy, uint dwData, IntPtr dwExtraInfo);
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint nFlags);
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int left, top, right, bottom; }
}
"@ -ErrorAction SilentlyContinue

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }
$logFile = Join-Path $LogDir ("auto_ui_{0}.log" -f (Get-Date -Format yyyyMMdd_HHmmss))
function Log($msg) {
    $line = "[{0:HH:mm:ss}] {1}" -f (Get-Date), $msg
    Write-Host $line
    Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Get-SldIM { return (Get-Process -Name sldIM -ErrorAction SilentlyContinue | Select-Object -First 1) }
function Test-SW2026 {
    # SSQ reg 会预植 HKLM\SOFTWARE\SolidWorks\SolidWorks 2026 (混合大小写壳)
    # 真正安装完成的铁证 = sldworks.exe 真文件存在
    foreach ($p in @(
        'C:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.exe',
        'D:\Program Files\SOLIDWORKS Corp\SOLIDWORKS\sldworks.exe',
        'C:\Program Files\SOLIDWORKS Corp26\SOLIDWORKS\sldworks.exe'
    )) {
        if (Test-Path $p) { return $true }
    }
    # 次要证据: 注册表 SOLIDWORKS 2026 (全大写, 且含 Setup/Installed key)
    try {
        $k = Get-Item 'HKLM:\SOFTWARE\SolidWorks\SOLIDWORKS 2026\Setup' -ErrorAction SilentlyContinue
        if ($k) { return $true }
    } catch { }
    return $false
}
function Test-Msiexec { return ((Get-Process -Name msiexec -ErrorAction SilentlyContinue) -ne $null) }

function Capture-HWND($hwnd) {
    $rect = New-Object AU+RECT
    [void][AU]::GetWindowRect($hwnd, [ref]$rect)
    $w = $rect.right - $rect.left; $h = $rect.bottom - $rect.top
    if ($w -le 0 -or $h -le 0) { return $null }
    $bmp = New-Object System.Drawing.Bitmap $w, $h
    $g = [System.Drawing.Graphics]::FromImage($bmp); $hdc = $g.GetHdc()
    [void][AU]::PrintWindow($hwnd, $hdc, 2); $g.ReleaseHdc($hdc); $g.Dispose()
    return @{ bmp = $bmp; rect = $rect; w = $w; h = $h }
}
function Hash-Bitmap($bmp) {
    $ms = New-Object System.IO.MemoryStream
    $bmp.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
    $bytes = $ms.ToArray(); $ms.Close()
    $sha = [System.Security.Cryptography.SHA256]::Create()
    return [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-','').Substring(0, 16)
}
function Click-Next($hwnd, $rect, $w, $h) {
    [void][AU]::ShowWindow($hwnd, 9); [void][AU]::BringWindowToTop($hwnd); [void][AU]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 400
    $x = [int]($rect.left + $w * $BtnXRatio)
    $y = [int]($rect.top  + $h * $BtnYRatio)
    [void][AU]::SetCursorPos($x, $y); Start-Sleep -Milliseconds 300
    [AU]::mouse_event(0x0002, 0, 0, 0, [IntPtr]::Zero)
    Start-Sleep -Milliseconds 100
    [AU]::mouse_event(0x0004, 0, 0, 0, [IntPtr]::Zero)
    Log "  ↘ clicked 下一步 at ($x, $y)"
}

Log "═══ sw2026 auto-UI sentinel start ═══"
Log "  interval=${IntervalSec}s  sticky_threshold=${StickyThreshold}  max=${MaxMinutes}min"
Log "  log: $logFile"
$deadline = (Get-Date).AddMinutes($MaxMinutes)
$lastHash = ''
$stickyCount = 0
$round = 0

while ((Get-Date) -lt $deadline) {
    $round += 1
    $p = Get-SldIM
    if (-not $p) { Log "sldIM gone · round $round · EXIT 0"; exit 0 }
    if (Test-SW2026) { Log "SW2026 registered · round $round · EXIT 0"; exit 0 }
    if (Test-Msiexec) { Log "round $round · msiexec running · sleep" ; Start-Sleep -Seconds $IntervalSec; continue }
    $cap = Capture-HWND $p.MainWindowHandle
    if (-not $cap) { Log "round $round · capture failed · skip"; Start-Sleep -Seconds $IntervalSec; continue }
    $hash = Hash-Bitmap $cap.bmp
    $ts = Get-Date -Format HHmmss
    $snap = Join-Path $LogDir "auto_snap_${ts}.png"
    $cap.bmp.Save($snap, [System.Drawing.Imaging.ImageFormat]::Png)
    $cap.bmp.Dispose()
    if ($hash -eq $lastHash) {
        $stickyCount += 1
        Log "round $round · hash=$hash sticky=$stickyCount · size=$($cap.w)x$($cap.h) · snap=$snap"
        if ($stickyCount -ge $StickyThreshold) {
            Log "  ⚠ stuck ${stickyCount}x · attempt auto-click 下一步"
            Click-Next $p.MainWindowHandle $cap.rect $cap.w $cap.h
            $stickyCount = 0
            Start-Sleep -Seconds 3
        }
    } else {
        Log "round $round · hash=$hash (changed) · snap=$snap"
        $stickyCount = 0
        $lastHash = $hash
    }
    Start-Sleep -Seconds $IntervalSec
}
Log "TIMEOUT after ${MaxMinutes}min · EXIT 1"
exit 1
