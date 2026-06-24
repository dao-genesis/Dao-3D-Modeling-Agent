@echo off
cd /d "%~dp0"
echo.
echo  ================================
echo   ModelHub 3D建模Agent中枢 v3.0
echo   万法归一 · 五层闭环
echo  ================================
echo.
echo   Dashboard: http://localhost:8872/
echo   VR Viewer: http://localhost:8872/viewer
echo   ORS6 Link: http://localhost:8871/
echo.
echo   00-本源_Origin   dao_kernel + dao_audit + dao_reverse
echo   10-反笙_FreeCAD  fc_reverse + fc_show + freecad_backend
echo   20-万法_Forge    forge_v3 + model_hub (本启动器)
echo   30-验证_Verify   _verify_*  _test_*  _e2e_*
echo   40/50/60/70      templates/demo/projects/world
echo.
start http://localhost:8872/
python "20-万法_Forge\model_hub.py" 8872
pause
