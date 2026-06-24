@echo off
chcp 65001 >nul
title SolidWorks 实测仿真 · 道法自然
echo ═══════════════════════════════════════════════
echo   锤式破碎机 · SolidWorks 实测仿真
echo ═══════════════════════════════════════════════
echo.
echo   七相实测:
echo     P1 连接 + 打开装配体
echo     P2 装配自检 (重建 + 组件)
echo     P3 干涉检测 (体级精确)
echo     P4 质量属性 (整机 + 单件)
echo     P5 配合关系图
echo     P6 运动算例 (主轴 1200rpm · 可选)
echo     P7 6 视图截图 + STEP/STL 导出
echo.
echo   提示: 请确保 SolidWorks 已启动并加载 Motion 插件 (P6 需要)
echo   若无 Motion 插件, 加 --skip-motion 参数
echo.
echo ───────────────────────────────────────────────

cd /d "%~dp0"
python sw_simulate.py %*

echo.
echo ───────────────────────────────────────────────
echo   完成. 报告: sw_api\sw_simulate_report.md
echo   截图: 交付包_最终\渲染图\sw_*.png
echo ───────────────────────────────────────────────
pause
