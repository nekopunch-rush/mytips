# AWS Account Checker - Windows Batch Test Wrapper
# 使い方: test_aws_account_check.bat
@echo off
setlocal

REM PowerShellのパスを特定
set "PS_PATH="
if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" (
    set "PS_PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
)
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
    set "PS_PATH=%ProgramFiles%\PowerShell\7\pwsh.exe"
)

if "%PS_PATH%"=="" (
    echo ERROR: PowerShellが見つかりません。
    exit /b 1
)

"%PS_PATH%" -ExecutionPolicy Bypass -File "%~dp0test_aws_account_check.ps1"
exit /b %ERRORLEVEL%
