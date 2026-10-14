@echo off
setlocal
cd /d "%~dp0"

echo =======================================================
echo          OpenXM-DVR - Build NetDvrSdk and CLI
echo =======================================================
echo.

set CSC=C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe

if not exist "%CSC%" (
    echo [ERROR] C# compiler not found at %CSC%
    echo Please ensure .NET Framework 4.5+ is installed.
    exit /b 1
)

if not exist "bin" mkdir "bin"

echo [1/2] Compiling NetDvrSdk.dll...
"%CSC%" /nologo /target:library /platform:x86 /out:bin\NetDvrSdk.dll src\NetDvrSdk\*.cs
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to compile NetDvrSdk.dll
    exit /b 1
)

copy /y "bin\NetDvrSdk.dll" "tools\DvrBackup\NetDvrSdk.dll" >nul

echo [2/2] Compiling DvrBackup.exe...
"%CSC%" /nologo /target:exe /platform:x86 /reference:bin\NetDvrSdk.dll /out:tools\DvrBackup\DvrBackup.exe tools\DvrBackup\Program.cs
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to compile DvrBackup.exe
    exit /b 1
)

echo.
echo [SUCCESS] Build complete! Executable is ready at:
echo   tools\DvrBackup\DvrBackup.exe
echo.
