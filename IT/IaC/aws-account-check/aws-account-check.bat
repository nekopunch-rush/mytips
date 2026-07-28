# AWS Account Checker - Windows Batch Wrapper
# 使い方: aws-account-check.bat <ディレクトリ> [設定ファイル]
@echo off
setlocal

REM PowerShellのパスを特定（PowerShell 5.1 / pwsh Core の両方対応）
set "PS_PATH="

REM PowerShell 5.1 (Windows 10/11 標準)
if exist "%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" (
    set "PS_PATH=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
)

REM PowerShell Core (pwsh) があれば優先
if exist "%ProgramFiles%\PowerShell\7\pwsh.exe" (
    set "PS_PATH=%ProgramFiles%\PowerShell\7\pwsh.exe"
)
if exist "%ProgramFiles(x86)%\PowerShell\7\pwsh.exe" (
    set "PS_PATH=%ProgramFiles(x86)%\PowerShell\7\pwsh.exe"
)

if "%PS_PATH%"=="" (
    echo ERROR: PowerShellが見つかりません。PowerShell 5.1以上またはPowerShell Coreをインストールしてください。
    exit /b 1
)

REM スクリプトのディレクトリを取得
set "SCRIPT_DIR=%~dp0"

REM 引数処理
if "%~1"=="" (
    echo 使い方: aws-account-check.bat <対象ディレクトリ> [設定ファイル]
    echo 例: aws-account-check.bat .\terraform\dev
    exit /b 1
)

set "TARGET_DIR=%~f1"

if "%~2"=="" (
    "%PS_PATH%" -ExecutionPolicy Bypass -File "%SCRIPT_DIR%aws-account-check.ps1" -TargetDir "%TARGET_DIR%"
) else (
    set "CONFIG_FILE=%~f2"
    "%PS_PATH%" -ExecutionPolicy Bypass -File "%SCRIPT_DIR%aws-account-check.ps1" -TargetDir "%TARGET_DIR%" -ConfigFile "%CONFIG_FILE%"
)

exit /b %ERRORLEVEL%
