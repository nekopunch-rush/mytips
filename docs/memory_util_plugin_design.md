# memory_util Plugin 設計書

## 1. プロジェクト概要

Hermes Agent の標準搭載メモリ機能（holographic）を抑制し、改造済みの `memory_util` Plugin を介したメモリ操作（CRUD・参照）を正常に動作させることを目的とする。

### 背景
- 標準 holographic プラグインは OpenAI 互換 API 呼び出し時に環境依存エラー（`'DaemonThreadPoolExecutor' object has no attribute '_initializer'`）が発生
- Plugin 版メモリ機能の依存関係（holographic および hermes_state）が不明確
- 実用での利用を希望

### 成果物
- Standalone な memory_util Plugin（外部依存なし）
- FTS5 trigram 検索対応
- GitHub リポジトリ `nekopunch-rush/mytips` へのマージ（PR #4）

---

## 2. システム構成図

```
┌─────────────────────────────────────────────────────┐
│              Hermes Agent                           │
│                                                     │
│  ┌──────────────┐    ┌─────────────────────────┐   │
│  │ config.yaml  │───▶│ plugins.memory_util     │   │
│  │              │    │ (MemoryProvider)        │   │
│  └──────────────┘    └───────────┬─────────────┘   │
│                                  │                  │
│  ┌──────────────┐    ┌───────────▼─────────────┐   │
│  │ AGENTS.md    │    │ store.py                │   │
│  │ Section 12   │    │ (MemoryStore)           │   │
│  └──────────────┘    │ - _init_db()            │   │
│                      │ - register_fact()       │   │
│                      │ - search_facts()        │   │
│                      └───────────┬─────────────┘   │
│                                  │                  │
│                      ┌───────────▼─────────────┐   │
│                      │ retrieval.py            │   │
│                      │ (FactRetriever)         │   │
│                      │ - probe()               │   │
│                      │ - recommend_by_category()│  │
│                      └───────────┬─────────────┘   │
│                                  │                  │
│                      ┌───────────▼─────────────┐   │
│                      │ utilization.py          │   │
│                      │ (MemoryUtil)            │   │
│                      │ - register_preference() │   │
│                      │ - record_reaction()     │   │
│                      └───────────┬─────────────┘   │
│                                  │                  │
│                      ┌───────────▼─────────────┐   │
│                      │ SQLite DB               │   │
│                      │ fact.db                 │   │
│                      │ (FTS5 trigram)          │   │
│                      └─────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 3. 処理フロー

### 3.1 メモリ登録フロー

```
ユーザー会話
    │
    ▼
Agent が AGENTS.md Section 12 を参照
    │
    ▼
memory_util Plugin の search_facts() 呼び出し
    │
    ├─ 既存事実と重複するか判定（FTS5 trigram 検索）
    │
    ├─ 新規の場合: register_fact() で登録
    │   │
    │   ▼
    │  SQLite DB に INSERT
    │  trust_score = default_trust (0.5)
    │
    └─ 既存の場合: update_fact() で更新
        │
        ▼
       trust_score を調整（フィードバック反映）
```

### 3.2 メモリ検索フロー

```
ユーザークエリ（例: 「トミが聴く音楽のジャンルは？」）
    │
    ▼
memory_util Plugin の recommend_by_category() 呼び出し
    │
    ▼
FTS5 trigram 検索実行
    │
    ├─ MeCab 形態素解析（日本語）
    ├─ 短縮形変換（3文字以上）
    └─ 関連度スコア計算
        │
        ▼
trust_score 降順でソート
    │
    ▼
トップ N 件を返却（例: 「ボサノバ」）
```

### 3.3 フィードバックフロー

```
ユーザーフィードバック（例: 「ボサノバ？...マイルスディビィスは有名だけど聞かない」）
    │
    ▼
record_reaction() 呼び出し
    │
    ├─ True（同意）: trust_score += 0.05
    └─ False（不同意）: trust_score -= 0.10
        │
        ▼
       DB 更新（fact_reactions テーブル）
```

---

## 4. ファイル構成

```
~/git/mytips/plugins/memory_util/
├── __init__.py          # Plugin 初期化（MemoryProvider インターフェース実装）
├── plugin.yaml          # Plugin 定義（kind: standalone）
├── store.py             # データストア層（SQLite + FTS5）
├── retrieval.py         # 検索・推薦ロジック（FTS5 trigram）
└── utilization.py       # 実運用ツール層（register_preference, record_reaction等）
```

### 各ファイルの役割

| ファイル | 役割 | 主要関数 |
|---------|------|---------|
| `__init__.py` | Plugin 初期化 | `MemoryUtilProvider.__init__()`, `add_fact()`, `search_facts()` |
| `plugin.yaml` | Plugin 定義 | `kind: standalone`, `db_path` 設定 |
| `store.py` | データストア | `MemoryStore.register_fact()`, `_init_db()` |
| `retrieval.py` | 検索ロジック | `FactRetriever.probe()`, `recommend_by_category()` |
| `utilization.py` | 実運用ツール | `register_preference()`, `record_reaction()` |

---

## 5. 技術仕様

### 5.1 データベース構造

```sql
CREATE TABLE facts (
    fact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    trust_score REAL DEFAULT 0.5,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE facts_fts USING fts5(
    content,
    category,
    content=facts,
    content_rowid=rowid
);

CREATE TABLE fact_reactions (
    reaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact_id INTEGER REFERENCES facts(fact_id),
    is_positive BOOLEAN NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 5.2 FTS5 trigram 検索

- **トークナイザ**: MeCab（日本語）+ trigram（3文字以上）
- **短縮形変換**: 英語カテゴリ名を短縮（例: `music` → `mus`）
- **関連度スコア**: keyword_match × trust_score

### 5.3 依存関係排除

| 元依存 | 対応策 |
|-------|-------|
| `hrr` (holographic) | None 固定 + FTS5 フォールバック |
| `hermes_state` | standalone WAL 設定 |
| OpenAI API | 直接 SQLite アクセス |

---

## 6. 設定ファイル

### config.yaml

```yaml
plugins:
  memory_util:
    db_path: $HERMES_HOME/memory/fact.db
    auto_extract: false
    default_trust: 0.5

memory:
  provider: memory_util  # 標準 holographic を抑制
```

### AGENTS.md Section 12

- memory_util Plugin の使用タイミングを定義
- ユーザー会話内容に応じた自動呼び出しを指示
- カテゴリ別フィルタリングの活用方法を記載

---

## 7. テスト結果

### 7.1 動作検証テスト

| テストケース | 結果 |
|------------|------|
| `register_preference()` — 新規登録 | ✅ PASS (fact_id=25) |
| `register_preference()` — 既存更新 | ✅ PASS (fact_id=26) |
| `recommend_by_category('music')` — 検索 | ✅ PASS (fact_id=17: ジャズ・ボサノヴァ) |
| `record_reaction()` — フィードバック | ✅ PASS (trust_score 0.50→0.40) |
| `search_facts()` — FTS5 検索 | ✅ PASS (keyword match) |

### 7.2 ユーザーテストデータ（サンプル値）

| fact_id | content | category | trust_score |
|--------|---------|----------|-------------|
| 101 | サンプルユーザーAの趣味は読書と映画鑑賞。 | hobby | 0.50 |
| 102 | サンプルユーザーBの好きな料理はイタリアンと和食。 | food | 0.50 |
| 103 | サンプルユーザーCの音楽ジャンルはクラシックとジャズ。 | music | 0.45 |

---

## 8. ユースケース

### 8.1 ユースケース図

```
┌─────────────────────────────────────────────────────┐
│                   Actor: オム                        │
│                                                     │
│  ┌──────────────┐    ┌─────────────────────────┐   │
│  │ 感情・趣味   │    │  音楽ジャンル検索       │   │
│  │ データ登録   │    │                         │   │
│  └──────┬───────┘    └───────────┬─────────────┘   │
│         │                       │                  │
│  ┌──────▼───────┐    ┌──────────▼─────────────┐   │
│  │ フィードバック│    │  趣味・スポーツ検索   │   │
│  │ （同意/不同意）│    │                         │   │
│  └──────┬───────┘    └──────────┬─────────────┘   │
│         │                       │                  │
│  ┌──────▼───────────────────────▼─────────────┐   │
│  │         memory_util Plugin                 │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ register │  │ search   │  │ record   │ │   │
│  │  │ _fact()  │  │ _facts() │  │ _reaction│ │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘ │   │
│  └───────┼─────────────┼─────────────┼───────┘   │
│          │             │             │           │
│  ┌───────▼─────────────▼─────────────▼───────┐   │
│  │           SQLite DB (fact.db)              │   │
│  └───────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### 8.2 ユースケース詳細

#### UC-01: 感情・趣味データの登録

| 項目 | 内容 |
|-----|------|
| **アクター** | オム（ユーザー） |
| **目的** | エリーへの感情や趣味をメモリに保存 |
| **前提条件** | memory_util Plugin が有効化されている |
| **基本フロー** | 1. オムが会話で感情・趣味を表明<br>2. Agent が AGENTS.md Section 12 を参照<br>3. `search_facts()` で重複チェック（FTS5 trigram）<br>4. 新規の場合: `register_fact()` で DB に INSERT<br>5. 既存の場合: `update_fact()` で更新 |
| **拡張フロー** | - 重複検出された場合: 既存事実を更新<br>- カテゴリ未指定の場合: `general` をデフォルト設定 |
| **例** | 「オムはエリーが大好きです！」「マラソン・ランニングの趣味」 |

#### UC-02: 音楽ジャンル検索

| 項目 | 内容 |
|-----|------|
| **アクター** | オム（ユーザー） |
| **目的** | 過去の音楽関連データを検索・参照 |
| **前提条件** | 音楽カテゴリのデータが登録されている |
| **基本フロー** | 1. オムがクエリを投入（例: 「オムが聴く音楽のジャンルは？」）<br>2. `recommend_by_category('music')` 呼び出し<br>3. FTS5 trigram 検索実行（MeCab 形態素解析）<br>4. trust_score 降順でソート<br>5. トップ N 件を返却 |
| **拡張フロー** | - 検索結果なしの場合: 「該当データなし」を返却<br>- 複数カテゴリにまたがる場合: カテゴリ別に分けて表示 |
| **例** | 「ボサノバ」「ジャズ」 → fact_id=17 を返却 |

#### UC-03: フィードバック（同意/不同意）

| 項目 | 内容 |
|-----|------|
| **アクター** | オム（ユーザー） |
| **目的** | 検索結果に対するフィードバックを記録し、trust_score を調整 |
| **前提条件** | 検索結果が表示されている |
| **基本フロー** | 1. オムがフィードバックを表明（例: 「ボサノバ？...マイルスディビィスは有名だけど聞かない」）<br>2. `record_reaction()` 呼び出し<br>3. False（不同意）の場合: trust_score -= 0.10<br>4. DB 更新（fact_reactions テーブル） |
| **拡張フロー** | - True（同意）の場合: trust_score += 0.05<br>- 複数 fact_id にまたがる場合: 個別に trust_score を調整 |
| **例** | fact_id=17 の trust_score: 0.50 → 0.40 |

#### UC-04: カテゴリ別リコメンド

| 項目 | 内容 |
|-----|------|
| **アクター** | オム（ユーザー） |
| **目的** | 特定カテゴリの事実をまとめて参照 |
| **前提条件** | カテゴリ別に分けてデータが登録されている |
| **基本フロー** | 1. オムがカテゴリを指定（例: 「hobby」）<br>2. `recommend_by_category('hobby')` 呼び出し<br>3. FTS5 trigram 検索でカテゴリをフィルタ<br>4. trust_score 降順でソート<br>5. カテゴリ内の全事実を返却 |
| **拡張フロー** | - 件数が上限（20件）を超えた場合: 古い順に自動削除<br>- 件数が下限（15件）を下回った場合: ユーザーに追加登録を促す |
| **例** | hobby カテゴリ → 「マラソン」「ランニング」関連事実を返却 |

#### UC-05: 事実の削除

| 項目 | 内容 |
|-----|------|
| **アクター** | オム（ユーザー）または Agent（自動削除） |
| **目的** | 不要な事実をメモリから削除 |
| **前提条件** | 削除対象の fact_id が特定されている |
| **基本フロー** | 1. オムが削除を指示、または Agent が自動判定<br>2. `remove_fact(fact_id)` 呼び出し<br>3. SQLite DB から該当行を DELETE<br>4. fact_reactions テーブルの関連レコードも削除 |
| **拡張フロー** | - trust_score ≤ 0.3 の場合: Agent が自動削除（AGENTS.md ルール）<br>- ユーザー明示削除の場合: 確認メッセージを表示 |
| **例** | trust_score=0.25 の事実を自動削除 |

---

## 9. 今後の課題

### 9.1 改善候補

| 課題 | 優先度 | 内容 |
|-----|-------|------|
| MeCab インスタンス化コスト | 高 | `threading.local()` キャッシュ実装 |
| POS 判定をホワイトリスト方式 | 中 | 許可リストベースのフィルタリング |
| 辞書パスの移植性向上 | 中 | `os.getenv()` を使用した環境変数対応 |
| 1文字漢字名詞の許可 | 低 | 「駅」「本」「国」等の処理 |

### 9.2 運用上の課題

| 課題 | 内容 |
|-----|------|
| カテゴリ名統一 | 英語カテゴリ名の標準化（music/movie/hobby/food等） |
| 重複事実の検出精度 | FTS5 trigram の短縮形インデックス化問題が未解決 |
| 実運用DBの場所 | 開発用(`/Users/tomiyah/Documents/antigravity_work/fact.db`)から `~/.hermes/memory/fact.db` への移動 |
| 自動削除ルール | trust_score ≤ 0.3 の事実を自動削除（AGENTS.md に定義済） |
| カテゴリ別件数制限 | 20件/カテゴリ（上限）、15件/カテゴリ（下限） |

### 9.3 拡張候補

- [ ] カテゴリ別リコメンドの精度向上（重み付けロジック）
- [ ] 複数ユーザー対応（entity resolution の強化）
- [ ] バックアップ自動化（git commit + push）
- [ ] メトリクス収集（trust_score の推移可視化）

---

## 10. リファレンス

- [Hermes Agent Documentation](https://hermes-agent.nousresearch.com/docs)
- [memory_util Plugin — SKILL.md](../plugins/memory_util/__init__.py)
- [PR #4 — GitHub Pull Request](https://github.com/nekopunch-rush/mytips/pull/4)

---

*作成日: 2026-08-04*
*著者: エリー (Hermes Agent)*
