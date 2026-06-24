@echo off
chcp 65001 >nul
title 全链路打通 · 道法自然 · 万法归宗
echo ═══════════════════════════════════════════════
echo   锤式破碎机 · 全链路打通 · 道法自然
echo ═══════════════════════════════════════════════
echo.
echo   Stage 0  环境锚定
echo   Stage 1  几何重建 (CadQuery)
echo   Stage 2  快速验证 (七相)
echo   Stage 3  运动学/动平衡
echo   Stage 4  SolidWorks 实测仿真 (需 SW 运行)
echo   Stage 5  报告聚合
echo.
echo   命令行参数 (可选):
echo     --skip-build      跳过几何重建 (复用 output_cq/)
echo     --skip-verify     跳过验证
echo     --skip-kinematic  跳过运动学
echo     --skip-sw         跳过 SW 实测仿真
echo     --skip-motion     SW 仿真内跳过运动算例
echo.
echo ───────────────────────────────────────────────

cd /d "%~dp0"
python dao_full_loop.py %*

echo.
echo ───────────────────────────────────────────────
echo   完成. 报告: _DAO_FULL_LOOP_REPORT.md
echo ───────────────────────────────────────────────
pause
