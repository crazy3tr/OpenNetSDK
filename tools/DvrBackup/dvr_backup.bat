@echo off
chcp 65001 >nul
title OpenXM-DVR - Backup Tool
cd /d "%~dp0"

echo =======================================================
echo          OpenXM-DVR - Hard Disk Backup Tool
echo =======================================================
echo.
echo 1) Download Latest Recordings and Convert to MP4
echo 2) Download All Recordings For Today (Channel 1)
echo 3) Download Past 7 Days (Incremental)
echo 4) Download Past 30 Days (Incremental)
echo 5) Continuous 100-Day Backup Mode
echo 6) List Disk Catalog (Without Downloading)
echo 7) Exit
echo.
set /p OPT="Select option (1-7): "

if "%OPT%"=="1" (
    DvrBackup.exe --mode download --channel 1 --days 1 --latest 5
) else if "%OPT%"=="2" (
    DvrBackup.exe --mode download --channel 1 --days 1
) else if "%OPT%"=="3" (
    DvrBackup.exe --mode download --channel 1 --days 7
) else if "%OPT%"=="4" (
    DvrBackup.exe --mode download --channel 1 --days 30
) else if "%OPT%"=="5" (
    DvrBackup.exe --mode download --channel 1 --days 100
) else if "%OPT%"=="6" (
    DvrBackup.exe --mode list --channel 1 --days 7
) else (
    exit /b
)

echo.
echo Done.
pause
