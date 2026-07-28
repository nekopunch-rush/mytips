# AWS Account Checker - Test Suite
# 使い方: pwsh -ExecutionPolicy Bypass -File ./test_aws_account_check.ps1

$BaseDir = "/Users/tomiyah"
$CheckScript = Join-Path $BaseDir "aws-account-check.ps1"
$ConfigFile  = Join-Path $BaseDir "aws_account_map.json"

# テスト対象ディレクトリ
$DevDir     = Join-Path $BaseDir "git/mytips/terraform/dev"
$ProdDir    = Join-Path $BaseDir "git/mytips/terraform/prod"

# テスト結果を保持
$TestResults = @()
$PassCount   = 0
$FailCount   = 0

function Run-Test {
    param(
        [string]$Name,
        [string]$TargetDir,
        [bool] $ExpectPass  # true=正常、false=エラー期待
    )

    Write-Host ""
    Write-Host "========================================" -ForegroundColor Cyan
    Write-Host "  TEST: $Name" -ForegroundColor Cyan
    Write-Host "========================================" -ForegroundColor Cyan

    # PowerShellスクリプトを実行し、出力をキャプチャ
    $Output = & pwsh -ExecutionPolicy Bypass -File $CheckScript `
        -TargetDir $TargetDir `
        -ConfigFile $ConfigFile 2>&1

    $ExitCode = $LASTEXITCODE
    $OutputStr = ($Output | Out-String).Trim()

    $ExpectLabel = if ($ExpectPass) { 'PASS' } else { 'FAIL (エラー検出)' }
    Write-Host "  対象ディレクトリ: $TargetDir" -ForegroundColor Gray
    Write-Host "  期待: $ExpectLabel" -ForegroundColor Gray
    Write-Host "  結果: exit code=$ExitCode" -ForegroundColor Gray

    if ($ExpectPass) {
        if ($ExitCode -eq 0) {
            Write-Host "  ✅ PASS" -ForegroundColor Green
            $script:PassCount++
        } else {
            Write-Host "  ❌ FAIL (期待: PASS, 実際: FAIL)" -ForegroundColor Red
            Write-Host $OutputStr -ForegroundColor Yellow
            $script:FailCount++
        }
    } else {
        if ($ExitCode -ne 0) {
            Write-Host "  ✅ PASS (エラー正しく検出)" -ForegroundColor Green
            $script:PassCount++
        } else {
            Write-Host "  ❌ FAIL (期待: FAIL, 実際: PASS) - エラーが検出されなかった" -ForegroundColor Red
            Write-Host $OutputStr -ForegroundColor Yellow
            $script:FailCount++
        }
    }

    # 出力を表示（エラー時は赤、正常時は緑）
    if ($ExitCode -ne 0) {
        Write-Host $OutputStr -ForegroundColor Red
    } else {
        Write-Host $OutputStr -ForegroundColor Green
    }

    # テスト結果を記録
    $TestResults += [PSCustomObject]@{
        Name           = $Name
        TargetDir      = $TargetDir
        ExpectPass     = $ExpectPass
        ActualExitCode = $ExitCode
        Output         = $OutputStr
    }
}

# ============================================
# テストケース定義
# ============================================

Write-Host "============================================" -ForegroundColor White
Write-Host "  AWS Account Checker - Test Suite" -ForegroundColor White
Write-Host "============================================" -ForegroundColor White

# TEST 1: devディレクトリ（正しいアカウントのみ）→ PASS期待
Run-Test -Name "TEST 1: devディレクトリ（正しいアカウントのみ）" `
         -TargetDir $DevDir `
         -ExpectPass $true

# TEST 2: prodディレクトリ（誤ったdevアカウント混入）→ FAIL期待
Run-Test -Name "TEST 2: prodディレクトリ（誤ったdevアカウント混入）" `
         -TargetDir $ProdDir `
         -ExpectPass $false

# TEST 3: 存在しないディレクトリ → FAIL期待
Run-Test -Name "TEST 3: 存在しないディレクトリ" `
         -TargetDir (Join-Path $BaseDir "nonexistent") `
         -ExpectPass $false

# TEST 4: 設定ファイルに定義されていないディレクトリ → PASS（スキップ）期待
$UnknownDir = Join-Path $BaseDir "git/mytips/terraform/unknown"
New-Item -ItemType Directory -Path $UnknownDir -Force | Out-Null
@"
provider "aws" {
  region     = "ap-northeast-1"
  account_id = "999888777666"
}
"@ | Set-Content (Join-Path $UnknownDir "main.tf")

Run-Test -Name "TEST 4: 設定ファイルに定義されていないディレクトリ" `
         -TargetDir $UnknownDir `
         -ExpectPass $true

# TEST 5: 空のディレクトリ → PASS期待
$EmptyDir = Join-Path $BaseDir "git/mytips/terraform/empty"
New-Item -ItemType Directory -Path $EmptyDir -Force | Out-Null

Run-Test -Name "TEST 5: 空のディレクトリ" `
         -TargetDir $EmptyDir `
         -ExpectPass $true

# ============================================
# テストサマリー
# ============================================

Write-Host ""
Write-Host "============================================" -ForegroundColor White
Write-Host "  テストサマリー" -ForegroundColor White
Write-Host "============================================" -ForegroundColor White

if ($FailCount -eq 0) {
    Write-Host "  ✅ 全テストパス！ ($PassCount/$($PassCount + $FailCount))" -ForegroundColor Green
} else {
    Write-Host "  ❌ $FailCount個のテストが失敗しました ($PassCount/$($PassCount + $FailCount))" -ForegroundColor Red
}

Write-Host ""
foreach ($Result in $TestResults) {
    $Status = if ($Result.ExpectPass -and $Result.ActualExitCode -eq 0) { "PASS" }
              elseif (-not $Result.ExpectPass -and $Result.ActualExitCode -ne 0) { "PASS" }
              else { "FAIL" }

    $Color = if ($Status -eq "PASS") { "Green" } else { "Red" }
    Write-Host "  [$Status] $($Result.Name)" -ForegroundColor $Color
}

Write-Host ""
exit $(if ($FailCount -eq 0) { 0 } else { 1 })
