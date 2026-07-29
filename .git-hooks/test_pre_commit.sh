#!/bin/sh
# AWS Account Checker - Git Hook Test Suite
# .git-hooks/pre-commit の動作をテストする

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || echo "$SCRIPT_DIR")

# テスト用一時リポジトリ（各テストで新規作成）
PASS_COUNT=0
FAIL_COUNT=0

# テスト結果を記録
run_test() {
    local name="$1"
    local expected_exit="$2"  # 0=PASS, 1=FAIL(エラー検出)
    local actual_exit="$3"

    if [ "$expected_exit" = "$actual_exit" ]; then
        echo "  ✅ PASS: $name (exit=$actual_exit)"
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        echo "  ❌ FAIL: $name (expected=$expected_exit, actual=$actual_exit)"
        FAIL_COUNT=$((FAIL_COUNT + 1))
    fi
}

# テスト用リポジトリをセットアップ（引数でディレクトリ指定）
setup_test_repo() {
    local repo="$1"
    mkdir -p "$repo" 2>/dev/null || true
    cd "$repo" 2>/dev/null
    git init -q 2>/dev/null
    git config user.email "test@test.com" 2>/dev/null
    git config user.name "Test User" 2>/dev/null

    # hooks を配置（テスト用リポジトリの .git/hooks に配置する）
    mkdir -p "$repo/.git/hooks" 2>/dev/null || true
    cp "$SCRIPT_DIR/pre-commit" "$repo/.git/hooks/pre-commit" 2>/dev/null || true
    chmod +x "$repo/.git/hooks/pre-commit" 2>/dev/null || true

    # aws-account-check.ps1 と設定ファイルを配置
    mkdir -p "$repo/IT/IaC/aws-account-check" 2>/dev/null || true
    cp "$REPO_ROOT/IT/IaC/aws-account-check/aws-account-check.ps1" \
       "$repo/IT/IaC/aws-account-check/" 2>/dev/null || true
    cp "$REPO_ROOT/IT/IaC/aws-account-check/aws_account_map.json" \
       "$repo/IT/IaC/aws-account-check/" 2>/dev/null || true
}

# テスト1: 正しいアカウントのみのコミット → PASS(0)
test_correct_account() {
    echo ""
    echo "========================================"
    echo "  TEST 1: 正しいアカウントのみのコミット"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    # devディレクトリを作成（正しいアカウントのみ）
    mkdir -p "$TEST_REPO/terraform/dev" 2>/dev/null || true
    cat > "$TEST_REPO/terraform/dev/main.tf" << 'EOF'
provider "aws" {
  region     = "ap-northeast-1"
  account_id = "111222333444"
}

resource "aws_s3_bucket" "dev-bucket" {
  bucket = "mytips-dev-bucket"
}
EOF

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add terraform/dev/ 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?
    echo "  [DEBUG] TEST 1: exit_code=$exit_code, pwd=$(pwd)" >&2

    echo "  期待: PASS (exit=0)"
    run_test "正しいアカウントのみのコミット" 0 "$exit_code"

    # cleanup for next test
    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# テスト2: 誤ったアカウントの混入 → FAIL(1)
test_wrong_account() {
    echo ""
    echo "========================================"
    echo "  TEST 2: 誤ったアカウントの混入"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    # prodディレクトリに誤ったdevアカウントを指定
    mkdir -p "$TEST_REPO/terraform/prod" 2>/dev/null || true
    cat > "$TEST_REPO/terraform/prod/main.tf" << 'EOF'
provider "aws" {
  region     = "ap-northeast-1"
  account_id = "111222333444"
}

resource "aws_s3_bucket" "prod-bucket" {
  bucket = "mytips-prod-bucket"
}
EOF

    # yamlファイルにも誤ったアカウント
    cat > "$TEST_REPO/terraform/prod/config.yaml" << 'EOF'
environment: prod
aws_account_id: "111222333444"
region: ap-northeast-1
EOF

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add terraform/prod/ 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?
    echo "  [DEBUG] TEST 2: exit_code=$exit_code, pwd=$(pwd), TEST_REPO=$TEST_REPO" >&2

    echo "  期待: FAIL (exit=1) - エラー検出"
    run_test "誤ったアカウントの混入" 1 "$exit_code"

    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# テスト3: 変更対象のファイルがない → PASS(0)（スキップ）
test_no_tf_files() {
    echo ""
    echo "========================================"
    echo "  TEST 3: .tf/.yaml ファイル以外のみ"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    # 普通のテキストファイルのみ（.tf/.yaml/.yml/.json 以外）
    echo "hello world" > "$TEST_REPO/readme.txt"

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add readme.txt 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?

    echo "  期待: PASS (exit=0) - チェック対象外"
    run_test ".tf/.yaml ファイル以外のみ" 0 "$exit_code"

    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# テスト4: 空コミット → PASS(0)
test_empty_commit() {
    echo ""
    echo "========================================"
    echo "  TEST 4: 空コミット（変更ファイルなし）"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add terraform/dev/ 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?

    echo "  期待: PASS (exit=0) - スキップ"
    run_test "空コミット" 0 "$exit_code"

    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# テスト5: 設定ファイルに定義されていないディレクトリ → PASS(0)（スキップ）
test_unknown_directory() {
    echo ""
    echo "========================================"
    echo "  TEST 5: 設定ファイルに定義されていないディレクトリ"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    # aws_account_map.json に定義されていないディレクトリ
    mkdir -p "$TEST_REPO/terraform/staging" 2>/dev/null || true
    cat > "$TEST_REPO/terraform/staging/main.tf" << 'EOF'
provider "aws" {
  region     = "ap-northeast-1"
  account_id = "999888777666"
}

resource "aws_s3_bucket" "staging-bucket" {
  bucket = "mytips-staging-bucket"
}
EOF

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add terraform/staging/ 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?

    echo "  期待: PASS (exit=0) - スキップ"
    run_test "設定ファイルに定義されていないディレクトリ" 0 "$exit_code"

    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# テスト6: 複数のディレクトリにまたがるコミット → 正しくチェック
test_multi_directory() {
    echo ""
    echo "========================================"
    echo "  TEST 6: 複数のディレクトリにまたがるコミット"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    # dev: 正しいアカウント
    mkdir -p "$TEST_REPO/terraform/dev" 2>/dev/null || true
    cat > "$TEST_REPO/terraform/dev/main.tf" << 'EOF'
provider "aws" {
  region     = "ap-northeast-1"
  account_id = "111222333444"
}

resource "aws_s3_bucket" "dev-bucket" {
  bucket = "mytips-dev-bucket"
}
EOF

    # prod: 誤ったdevアカウント混入
    mkdir -p "$TEST_REPO/terraform/prod" 2>/dev/null || true
    cat > "$TEST_REPO/terraform/prod/main.tf" << 'EOF'
provider "aws" {
  region     = "ap-northeast-1"
  account_id = "111222333444"
}

resource "aws_s3_bucket" "prod-bucket" {
  bucket = "mytips-prod-bucket"
}
EOF

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add terraform/ 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?

    echo "  期待: FAIL (exit=1) - prodの誤ったアカウント検出"
    run_test "複数のディレクトリにまたがるコミット" 1 "$exit_code"

    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# テスト7: jsonファイル内のアカウントIDも検出 → FAIL(1)
test_json_account() {
    echo ""
    echo "========================================"
    echo "  TEST 7: jsonファイル内のアカウントID検出"
    echo "========================================"

    TEST_REPO=$(mktemp -d 2>/dev/null || mktemp -d -t test-aws-hook)
    setup_test_repo "$TEST_REPO"

    mkdir -p "$TEST_REPO/terraform/prod" 2>/dev/null || true
    cat > "$TEST_REPO/terraform/prod/settings.json" << 'EOF'
{
  "environment": "prod",
  "aws_account_id": "111222333444",
  "region": "ap-northeast-1"
}
EOF

    # git add でステージングしてから hook を実行（git diff --cached が必要）
    cd "$TEST_REPO" 2>/dev/null && git add terraform/prod/ 2>/dev/null
    cd "$TEST_REPO" 2>/dev/null; GIT_DIR="$TEST_REPO/.git" PWD="$TEST_REPO" bash "$TEST_REPO/.git/hooks/pre-commit" 2>/dev/null
    exit_code=$?

    echo "  期待: FAIL (exit=1) - json内のアカウントID検出"
    run_test "jsonファイル内のアカウントID検出" 1 "$exit_code"

    rm -rf "$TEST_REPO" 2>/dev/null || true
}

# ============================================
# テスト実行
# ============================================

echo "============================================"
echo "  Git Hook Test Suite"
echo "============================================"

test_correct_account
test_wrong_account
test_no_tf_files
test_empty_commit
test_unknown_directory
test_multi_directory
test_json_account

# ============================================
# サマリー
# ============================================

echo ""
echo "============================================"
echo "  テストサマリー"
echo "============================================"

TOTAL=$((PASS_COUNT + FAIL_COUNT))
if [ $FAIL_COUNT -eq 0 ]; then
    echo "  ✅ 全テストパス！ ($PASS_COUNT/$TOTAL)"
else
    echo "  ❌ $FAIL_COUNT個のテストが失敗 ($PASS_COUNT/$TOTAL)"
fi

echo ""
if [ $FAIL_COUNT -eq 0 ]; then
    exit 0
else
    exit 1
fi
