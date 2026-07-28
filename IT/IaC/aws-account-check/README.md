# AWS Account Checker

ディレクトリごとに許可されたAWSアカウントIDを管理し、間違ったアカウントでリソースを作成するミスをコミット時点で検出します。

## 動作原理

`aws_account_map.json` にディレクトリ名と許可されたAWSアカウントIDの対応を定義し、対象ディレクトリ内の `.tf`, `.yaml`, `.yml`, `.json` ファイルから `account_id` / `aws_account_id` の値を抽出して照合します。

## 対応OS

| OS | 要件 |
|---|---|
| **macOS** | PowerShell (Homebrew: `pwsh`) が必要 |
| **Windows** | PowerShell 5.1 以上 / PowerShell Core (`pwsh`) で動作。外部依存なし |

## ファイル構成

```
aws-account-check/
├── aws-account-check.ps1    # メインスクリプト（Mac/Windows共通）
├── test_aws_account_check.ps1  # テストスイート
├── aws_account_map.json     # ディレクトリ→アカウントIDマッピング
└── README.md                # このファイル
```

## 使い方

### 基本的な実行

```powershell
# Mac (PowerShell Core)
pwsh -ExecutionPolicy Bypass -File ./aws-account-check.ps1 -TargetDir ./terraform/dev

# Windows (PowerShell 5.1 / PowerShell Core)
powershell -ExecutionPolicy Bypass -File .\aws-account-check.ps1 -TargetDir .\terraform\dev
```

### 設定ファイルを指定する場合

```powershell
pwsh -ExecutionPolicy Bypass -File ./aws-account-check.ps1 `
    -TargetDir ./terraform/prod `
    -ConfigFile ./custom_account_map.json
```

### テストスイート実行

```powershell
pwsh -ExecutionPolicy Bypass -File ./test_aws_account_check.ps1
```

## 設定ファイル形式 (`aws_account_map.json`)

```json
{
  "dev":   ["111222333444", "555666777888"],
  "prod":  ["333444555666", "777888999000"]
}
```

- キー: ディレクトリ名（`aws_account_map.json` と同じ階層にあるディレクトリ）
- 値: 許可されたAWSアカウントIDの配列（12桁の数字）

## pre-commit hook 設定例

`.pre-commit-config.yaml` に追加:

```yaml
repos:
  - repo: local
    hooks:
      - id: aws-account-check
        name: AWS Account Check
        entry: pwsh -ExecutionPolicy Bypass -File ./IT/IaC/aws-account-check/aws-account-check.ps1
        language: system
        files: '\.(tf|yaml|yml|json)$'
```

## 正規表現で検出するパターン

以下の形式で記述されたアカウントIDを検出します:

```
account_id = "123456789012"
aws_account_id: 123456789012
"account_id": "123456789012"
```

## 注意事項

- `aws_account_map.json` に定義されていないディレクトリはスキップされます（警告出力のみ）
- 空のディレクトリも正常終了します
- WindowsではPowerShell 5.1以上、または `pwsh` (PowerShell Core) が必要です
