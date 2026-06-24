@echo off
REM ===========================================================================
REM   Wanfa entry script (ASCII-only REM to avoid codepage noise)
REM ===========================================================================
REM
REM Usage:
REM   .cmd                        help
REM   .cmd summary                system status
REM   .cmd verify                 lazy-load smoke test
REM   .cmd intent "intent text"   intent dispatcher
REM   .cmd reverse "query"        reverse-outer (20 platform search)
REM   .cmd adapt file.FCStd k=v   reverse-inner (edit and replay)
REM   .cmd show file.step         show in FreeCAD GUI
REM   .cmd live                   SolidWorks live connect
REM   .cmd audit file.step        8-layer audit
REM   .cmd manifest               print manifest
REM ===========================================================================

setlocal
pushd "%~dp0"

REM Switch to UTF-8 codepage so Chinese I/O prints correctly (redirect noise)
chcp 65001 >nul 2>&1

if "%~1"=="" (
    python 万法.py
) else (
    python 万法.py %*
)
set RC=%ERRORLEVEL%

popd
endlocal & exit /b %RC%
