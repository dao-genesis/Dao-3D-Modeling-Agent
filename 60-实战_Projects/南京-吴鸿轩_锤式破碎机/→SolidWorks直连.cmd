@echo off
chcp 65001 >nul
title SolidWorks 直连探针 · 道法自然
echo ═══════════════════════════════════════════
echo   SolidWorks COM 直连 · 推进一切
echo ═══════════════════════════════════════════
echo.

cd /d "%~dp0"
python sw_probe.py

echo.
echo ───────────────────────────────────────────
echo   完成. 结果已写入 sw_api\sw_probe_log.json
echo   截图已保存至 交付包_最终\渲染图\
echo ───────────────────────────────────────────
pause
