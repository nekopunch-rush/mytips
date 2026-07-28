# AWS Account Checker for PowerShell
# 使い方: .\aws-account-check.ps1 -TargetDir <ディレクトリ> [-ConfigFile <設定ファイル>]

param(
    [Parameter(Mandatory=$true)]
    [string]$TargetDir,

    [string]$ConfigFile = "aws_account_map.json"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# 引数チェック
if (-not (Test-Path $TargetDir)) {
    Write-Host "❌ ディレクトリ '$TargetDir' が見つかりません" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ConfigFile)) {
    Write-Host "❌ 設定ファイル '$ConfigFile' が見つかりません" -ForegroundColor Red
    exit 1
}

# ディレクトリ名を取得（最終要素）
$DirName = (Get-Item $TargetDir).Name

# 設定ファイルを読み込み、ディレクトリ名に対応するアカウントIDリストを取得
$Config = Get-Content $ConfigFile -Raw | ConvertFrom-Json

if (-not $Config.PSObject.Properties.Name.Contains($DirName)) {
    Write-Host "⚠️  ディレクトリ '$DirName' は設定ファイルに定義されていません。スキップします。" -ForegroundColor Yellow
    exit 0
}

$AllowedAccounts = $Config.$DirName

# 対象ファイルを検索（.tf, .yaml, .yml, .json）
$TargetFiles = Get-ChildItem -Path $TargetDir -Recurse -File |
    Where-Object { $_.Extension -in @('.tf', '.yaml', '.yml', '.json') }

$ErrorList = @()
# account_id / aws_account_id の値として12桁の数字を抽出する正規表現
$Pattern = '(?i)(?:account_id|aws_account_id)\s*[":\s=]*\s*"?(\d{12})"?'

foreach ($File in $TargetFiles) {
    try {
        $Content = Get-Content $File.FullName -Raw -ErrorAction Stop
    } catch {
        continue
    }

    # 12桁の数字（AWSアカウントID）を抽出
    $Matches = [regex]::Matches($Content, $Pattern) | ForEach-Object { $_.Groups[1].Value }

    foreach ($Account in $Matches) {
        if ($AllowedAccounts -notcontains $Account) {
            $ErrorList += "❌ $($File.FullName): AWSアカウント '$Account' はディレクトリ '$DirName' の定義済みアカウントと一致しません"
        }
    }
}

# エラーがあれば出力して終了
if ($ErrorList.Count -gt 0) {
    Write-Host ""
    Write-Host "🚨 AWS Account Check FAILED" -ForegroundColor Red
    Write-Host "   対象ディレクトリ: $TargetDir" -ForegroundColor White
    Write-Host ""
    foreach ($Err in $ErrorList) {
        Write-Host "   $Err" -ForegroundColor Red
    }
    exit 1
}

Write-Host "✅ 全ファイルで正しいAWSアカウントを使用しています" -ForegroundColor Green
exit 0
