"""
SQLite-backed fact store with entity resolution and trust scoring.
Single-user Hermes memory store plugin.

Enhanced with MeCab Japanese tokenization for FTS5 full-text search.
Falls back to regex-based entity extraction when MeCab is unavailable.
"""

import re
import sqlite3
import threading
from pathlib import Path

try:
    import MeCab  # type: ignore[import-untyped]
    _MECAB_AVAILABLE = True
except ImportError:
    MeCab = None  # type: ignore[assignment]
    _MECAB_AVAILABLE = False

import os
import threading

_MECAB_LOCAL = threading.local()


def _get_mecab_tagger():
    """Get thread-local MeCab Tagger instance (lazy initialization)."""
    if not _MECAB_AVAILABLE or MeCab is None:  # type: ignore[redundant-cast]
        return None
    if not hasattr(_MECAB_LOCAL, "tagger"):
        try:
            dic_path = os.getenv(
                "MECAB_DIC_PATH", "/opt/homebrew/lib/mecab/dic/ipadic"
            )
            if os.path.exists(dic_path):
                _MECAB_LOCAL.tagger = MeCab.Tagger(f"-d {dic_path}")  # type: ignore[union-attr]
            else:
                _MECAB_LOCAL.tagger = MeCab.Tagger()  # type: ignore[union-attr]
        except Exception:
            _MECAB_LOCAL.tagger = None  # type: ignore[assignment]
    return _MECAB_LOCAL.tagger  # type: ignore[return-value]


_MECAB_DIC_PATH = "/opt/homebrew/lib/mecab/dic/ipadic"

# Standalone: no holographic dependency. HRR vectors are optional and skipped when unavailable.
hrr = None  # type: ignore[assignment]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    fact_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    content         TEXT NOT NULL UNIQUE,
    category        TEXT DEFAULT 'general',
    tags            TEXT DEFAULT '',
    trust_score     REAL DEFAULT 0.5,
    retrieval_count INTEGER DEFAULT 0,
    helpful_count   INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    hrr_vector      BLOB
);

CREATE TABLE IF NOT EXISTS entities (
    entity_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    entity_type TEXT DEFAULT 'unknown',
    aliases     TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_entities (
    fact_id   INTEGER REFERENCES facts(fact_id),
    entity_id INTEGER REFERENCES entities(entity_id),
    PRIMARY KEY (fact_id, entity_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
    USING fts5(content, tags, tokenize=trigram, content=facts, content_rowid=fact_id);

CREATE INDEX IF NOT EXISTS idx_facts_trust    ON facts(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_facts_category ON facts(category);
CREATE INDEX IF NOT EXISTS idx_entities_name  ON entities(name);

CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content)
        VALUES ('delete', old.fact_id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, content)
        VALUES ('delete', old.fact_id, old.content);
    INSERT INTO facts_fts(rowid, content)
        VALUES (new.fact_id, new.content);
END;

CREATE TABLE IF NOT EXISTS memory_banks (
    bank_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    bank_name  TEXT NOT NULL UNIQUE,
    vector     BLOB NOT NULL,
    dim        INTEGER NOT NULL,
    fact_count INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Trust adjustment constants
_HELPFUL_DELTA   =  0.05
_UNHELPFUL_DELTA = -0.10
_TRUST_MIN       =  0.0
_TRUST_MAX       =  1.0

# Entity extraction patterns
_RE_CAPITALIZED  = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b')
_RE_DOUBLE_QUOTE = re.compile(r'"([^"]+)"')
_RE_SINGLE_QUOTE = re.compile(r"'([^']+)'")
_RE_AKA          = re.compile(
    r'(\w+(?:\s+\w+)*)\s+(?:aka|also known as)\s+(\w+(?:\s+\w+)*)',
    re.IGNORECASE,
)


def _clamp_trust(value: float) -> float:
    return max(_TRUST_MIN, min(_TRUST_MAX, value))


class MemoryStore:
    """SQLite-backed fact store with entity resolution and trust scoring."""

    # --- Process-wide shared connection registry -------------------------
    # SQLite permits only one writer at a time. Each MemoryStore instance used
    # to open its own connection guarded by its own RLock, so the several
    # providers that coexist in one process (the main agent plus every
    # delegate_task subagent) raced as independent WAL writers. Combined with
    # writes that were not rolled back on error, one connection could leave an
    # open write transaction that pinned the write lock and made every other
    # connection's write fail with "database is locked" for the full busy
    # timeout. All instances for the same database now share ONE connection and
    # ONE re-entrant lock, so access is fully serialized and cross-connection
    # contention is impossible. The shared connection is refcounted, so closing
    # one instance never tears the connection out from under a live sibling.
    _shared: dict = {}
    _shared_guard = threading.Lock()

    def __init__(
        self,
        db_path: "str | Path | None" = None,
        default_trust: float = 0.5,
        hrr_dim: int = 1024,
    ) -> None:
        if db_path is None:
            from hermes_constants import get_hermes_home
            db_path = str(get_hermes_home() / "memory_store.db")
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.default_trust = _clamp_trust(default_trust)
        self.hrr_dim = hrr_dim if hrr else 0

        # Acquire (or open) the process-wide shared connection for this DB.
        # resolve() (not just expanduser) so symlinked/relative paths to the
        # same file share ONE connection instead of silently reintroducing
        # the multi-writer contention this registry exists to prevent.
        try:
            self._key = str(self.db_path.resolve())
        except OSError:
            self._key = str(self.db_path)
        with MemoryStore._shared_guard:
            entry = MemoryStore._shared.get(self._key)
            if entry is None:
                conn = sqlite3.connect(
                    self._key,
                    check_same_thread=False,
                    timeout=10.0,
                    # Autocommit: every statement is its own transaction, so a
                    # write that raises mid-method can never leave a dangling
                    # transaction (and its write lock) open. The explicit
                    # commit() calls below become harmless no-ops.
                    isolation_level=None,
                )
                conn.row_factory = sqlite3.Row
                entry = {"conn": conn, "lock": threading.RLock(), "refs": 0, "ready": False}
                MemoryStore._shared[self._key] = entry
            entry["refs"] += 1
            self._entry = entry
            self._conn = entry["conn"]
            self._lock = entry["lock"]

        # Initialise the schema once per shared connection.
        with self._lock:
            if not self._entry["ready"]:
                self._init_db()
                self._entry["ready"] = True

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        """Create tables, indexes, and triggers if they do not exist. Enable WAL mode."""
        # Standalone: enable WAL mode directly (no hermes_state dependency)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass  # Some SQLite builds don't support WAL — degrade gracefully
        self._conn.executescript(_SCHEMA)
        # Migrate: add hrr_vector column if missing (safe for existing databases)
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(facts)").fetchall()}
        if "hrr_vector" not in columns:
            self._conn.execute("ALTER TABLE facts ADD COLUMN hrr_vector BLOB")
        
        # Migrate: switch FTS5 tokenizer from default (unicode61) to trigram for Bi-gram support
        # This requires dropping and recreating the FTS5 table with new tokenizer
        try:
            # Check if facts_fts exists and needs migration to trigram
            fts_info = self._conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='facts_fts'"
            ).fetchone()
            
            # Migrate if: table doesn't exist, OR tokenize=trigram is not set
            sql_str = fts_info[0].lower() if fts_info else ""
            if not fts_info or "tokenize=trigram" not in sql_str:
                with self._conn:  # Transactional operation
                    # Drop old FTS5 table (safe: external content table, real data stays in facts)
                    self._conn.execute("DROP TABLE IF EXISTS facts_fts")
                    # Recreate with trigram tokenizer (Bi-gram equivalent)
                    self._conn.executescript("""
                        CREATE VIRTUAL TABLE facts_fts
                            USING fts5(content, tags, tokenize=trigram, content=facts, content_rowid=fact_id);
                    """)
                    
                    # Rebuild index from facts table (required after CREATE)
                    self._conn.execute("INSERT INTO facts_fts(facts_fts) VALUES('rebuild');")
                    
                self._conn.commit()
        except Exception:
            # If migration fails, continue with existing setup
            pass
        
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_fact(
        self,
        content: str,
        category: str = "general",
        tags: str = "",
    ) -> int:
        """Insert a fact and return its fact_id.

        Deduplicates by content (UNIQUE constraint). On duplicate, returns
        the existing fact_id without modifying the row. Extracts entities from
        the content and links them to the fact.
        """
        with self._lock:
            content = content.strip()
            if not content:
                raise ValueError("content must not be empty")

            try:
                cur = self._conn.execute(
                    """
                    INSERT INTO facts (content, category, tags, trust_score)
                    VALUES (?, ?, ?, ?)
                    """,
                    (content, category, tags, self.default_trust),
                )
                self._conn.commit()
                fact_id: int = cur.lastrowid  # type: ignore[assignment]
            except sqlite3.IntegrityError:
                # Duplicate content — return existing id
                row = self._conn.execute(
                    "SELECT fact_id FROM facts WHERE content = ?", (content,)
                ).fetchone()
                return int(row["fact_id"])

            # Entity extraction and linking
            entities = self._extract_entities(content)
            for name in entities:
                entity_id = self._resolve_entity(name)
                self._link_fact_entity(fact_id, entity_id)

            # Build combined FTS5 content: original text + compound nouns for better recall
            combined_text = ' '.join([content] + entities) if entities else content
            self._conn.execute(
                "INSERT INTO facts_fts(rowid, content) VALUES (?, ?)",
                (fact_id, combined_text),
            )

            # Compute HRR vector after entity linking (no-op when hrr is unavailable)
            self._compute_hrr_vector(fact_id, content)
            self._rebuild_bank(category)

            return fact_id

    def search_facts(
        self,
        query: str,
        category: str | None = None,
        min_trust: float = 0.3,
        limit: int = 10,
    ) -> list[dict]:
        """Full-text search over facts using FTS5 with hybrid MATCH/LIKE.

        3+ character queries use FTS5 MATCH (index-based, fast).
        2 or fewer characters fall back to LIKE '%keyword%' (full scan, but fast on modern hardware).
        This ensures base words like '東京', 'AI' are searchable alongside compound nouns.

        Returns a list of fact dicts ordered by FTS5 rank, then trust_score
        descending. Also increments retrieval_count for matched facts.
        """
        with self._lock:
            query = query.strip()
            if not query:
                return []

            # FTS5 AND-joins tokens by default, which zeroes out recall on
            # natural-language queries. Use standalone sanitizer (stopword drop
            # + OR-join content tokens). Import with fallback for direct execution.

            try:
                from .retrieval import FactRetriever
            except ImportError:
                from retrieval import FactRetriever

            match_query = FactRetriever._sanitize_fts_query(query)
            category_clause = ""
            if category is not None:
                category_clause = "AND f.category = ?"

            # Hybrid search: 3+ chars use FTS5 MATCH, 2 or fewer use LIKE fallback
            if len(query) >= 3:
                # FTS5 MATCH (index-based, fast)
                sql = f"""
                    SELECT f.fact_id, f.content, f.category, f.tags,
                           f.trust_score, f.retrieval_count, f.helpful_count,
                           f.created_at, f.updated_at
                    FROM facts f
                    JOIN facts_fts fts ON fts.rowid = f.fact_id
                    WHERE facts_fts MATCH ?
                      AND f.trust_score >= {min_trust}
                      {category_clause}
                    ORDER BY fts.rank, f.trust_score DESC
                    LIMIT ?
                """
                params: list = [match_query, limit]
                if category is not None:
                    params.append(category)
            else:
                # LIKE fallback for short queries (2 chars or less)
                # Full scan but fast on modern hardware (ms-level for ~10k rows)
                sql = f"""
                    SELECT fact_id, content, category, tags,
                           trust_score, retrieval_count, helpful_count,
                           created_at, updated_at
                    FROM facts
                    WHERE content LIKE ?
                      AND trust_score >= {min_trust}
                      {category_clause}
                    ORDER BY fact_id
                    LIMIT ?
                """
                params = [f'%{query}%', limit]
                if category is not None:
                    params.append(category)

            rows = self._conn.execute(sql, params).fetchall()
            results = [self._row_to_dict(r) for r in rows]

            if results:
                ids = [r["fact_id"] for r in results]
                placeholders = ",".join("?" * len(ids))
                self._conn.execute(
                    f"UPDATE facts SET retrieval_count = retrieval_count + 1 WHERE fact_id IN ({placeholders})",
                    ids,
                )
                self._conn.commit()

            return results

    def update_fact(
        self,
        fact_id: int,
        content: str | None = None,
        trust_delta: float | None = None,
        tags: str | None = None,
        category: str | None = None,
    ) -> bool:
        """Partially update a fact. Trust is clamped to [0, 1].

        Returns True if the row existed, False otherwise.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT fact_id, trust_score FROM facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
            if row is None:
                return False

            assignments: list[str] = ["updated_at = CURRENT_TIMESTAMP"]
            params: list = []

            if content is not None:
                assignments.append("content = ?")
                params.append(content.strip())
            if tags is not None:
                assignments.append("tags = ?")
                params.append(tags)
            if category is not None:
                assignments.append("category = ?")
                params.append(category)
            if trust_delta is not None:
                new_trust = _clamp_trust(row["trust_score"] + trust_delta)
                assignments.append("trust_score = ?")
                params.append(new_trust)

            params.append(fact_id)
            self._conn.execute(
                f"UPDATE facts SET {', '.join(assignments)} WHERE fact_id = ?",
                params,
            )
            self._conn.commit()

            # If content changed, re-extract entities
            if content is not None:
                self._conn.execute(
                    "DELETE FROM fact_entities WHERE fact_id = ?", (fact_id,)
                )
                for name in self._extract_entities(content):
                    entity_id = self._resolve_entity(name)
                    self._link_fact_entity(fact_id, entity_id)
                self._conn.commit()

            # Recompute HRR vector if content changed (no-op when hrr is unavailable)
            if content is not None:
                self._compute_hrr_vector(fact_id, content)
            # Rebuild bank for relevant category
            cat = category or self._conn.execute(
                "SELECT category FROM facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()["category"]
            self._rebuild_bank(cat)

            return True

    def remove_fact(self, fact_id: int) -> bool:
        """Delete a fact and its entity links. Returns True if the row existed."""
        with self._lock:
            row = self._conn.execute(
                "SELECT fact_id, category FROM facts WHERE fact_id = ?", (fact_id,)
            ).fetchone()
            if row is None:
                return False

            self._conn.execute(
                "DELETE FROM fact_entities WHERE fact_id = ?", (fact_id,)
            )
            self._conn.execute("DELETE FROM facts WHERE fact_id = ?", (fact_id,))
            self._conn.commit()
            self._rebuild_bank(row["category"])
            return True

    def list_facts(
        self,
        category: str | None = None,
        min_trust: float = 0.0,
        limit: int = 50,
    ) -> list[dict]:
        """Browse facts ordered by trust_score descending.

        Optionally filter by category and minimum trust score.
        """
        with self._lock:
            params: list = [min_trust]
            category_clause = ""
            if category is not None:
                category_clause = "AND category = ?"
                params.append(category)
            params.append(limit)

            sql = f"""
                SELECT fact_id, content, category, tags, trust_score,
                       retrieval_count, helpful_count, created_at, updated_at
                FROM facts
                WHERE trust_score >= ?
                  {category_clause}
                ORDER BY trust_score DESC
                LIMIT ?
            """
            rows = self._conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def record_feedback(self, fact_id: int, helpful: bool) -> dict:
        """Record user feedback and adjust trust asymmetrically.

        helpful=True  -> trust += 0.05, helpful_count += 1
        helpful=False -> trust -= 0.10

        Returns a dict with fact_id, old_trust, new_trust, helpful_count.
        Raises KeyError if fact_id does not exist.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT fact_id, trust_score, helpful_count FROM facts WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"fact_id {fact_id} not found")

            old_trust: float = row["trust_score"]
            delta = _HELPFUL_DELTA if helpful else _UNHELPFUL_DELTA
            new_trust = _clamp_trust(old_trust + delta)

            helpful_increment = 1 if helpful else 0
            self._conn.execute(
                """
                UPDATE facts
                SET trust_score    = ?,
                    helpful_count  = helpful_count + ?,
                    updated_at     = CURRENT_TIMESTAMP
                WHERE fact_id = ?
                """,
                (new_trust, helpful_increment, fact_id),
            )
            self._conn.commit()

            return {
                "fact_id":      fact_id,
                "old_trust":    old_trust,
                "new_trust":    new_trust,
                "helpful_count": row["helpful_count"] + helpful_increment,
            }

    # ------------------------------------------------------------------
    # Entity helpers
    # ------------------------------------------------------------------

    _JAPANESE_RE = re.compile(r"[\u3041-\u3096\u30A1-\u30FA\u4E00-\u9FFF]")
    _KANJI_RE = re.compile(r"^[\u4E00-\u9FFF]$")
    _SKIP_NOUN_SUBTYPES = {
        "代名詞", "非自立", "数", "接続詞的", "動詞非自立的",
        "接尾", "特殊",  # AGY: 追加 - suffixes and special tokens
    }

    _ENGLISH_STOP_WORDS = {
        "a", "about", "above", "after", "again", "against", "all", "am",
        "an", "and", "any", "are", "aren't", "as", "at", "be", "because",
        "been", "before", "being", "below", "between", "both", "but", "by",
        "can't", "cannot", "could", "couldn't", "did", "didn't", "do",
        "does", "doesn't", "doing", "don't", "down", "during", "each",
        "few", "for", "from", "further", "had", "hadn't", "has", "hasn't",
        "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
        "here", "here's", "hers", "herself", "him", "himself", "his",
        "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in",
        "into", "is", "isn't", "it", "it's", "its", "itself", "let's",
        "like", "likes", "me", "more", "most", "mustn't", "my", "myself",
        "no", "nor", "not", "of", "off", "on", "once", "only", "or",
        "other", "ought", "our", "ours", "ourselves", "out", "over", "own",
        "same", "shan't", "she", "she'd", "she'll", "she's", "should",
        "shouldn't", "so", "some", "such", "than", "that", "that's", "the",
        "their", "theirs", "them", "themselves", "then", "there", "there's",
        "these", "they", "they'd", "they'll", "they're", "they've", "this",
        "those", "through", "to", "too", "under", "until", "up", "very",
        "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
        "weren't", "what", "what's", "when", "when's", "where", "where's",
        "which", "while", "who", "who's", "whom", "why", "why's", "with",
        "won't", "work", "works", "worked", "would", "wouldn't", "you",
        "you'd", "you'll", "you're", "you've", "your", "yours", "yourself",
        "yourselves"
    }

    def _parse_japanese_entities(self, text: str) -> list[dict]:
        """Extract noun entities from Japanese text using MeCab.

        Uses whitelisting approach: only 名詞 (noun) major POS is kept,
        with subtypes like 代名詞/非自立/数/接続詞的/接尾/特殊 excluded.
        Single kanji characters are preserved; single hiragana/alphanumeric
        characters are excluded. English stop words are filtered out.

        Returns list of dicts with keys: 'surface', 'pos_sub1', 'char_start', 'char_end'.
        Returns empty list if MeCab is unavailable or parsing fails.
        """
        tagger = _get_mecab_tagger()
        if tagger is None:
            return []

        try:
            node = tagger.parseToNode(text)
        except Exception:
            return []

        if node is None:
            return []

        seen: set[str] = set()
        entities: list[dict] = []
        char_offset = 0

        while node:
            surface = node.surface
            feature = node.feature

            # Skip EOS (BOS/EOS marker)
            if surface == "EOS" or feature.startswith("BOS"):
                node = node.next
                continue

            pos_parts = feature.split(",")
            pos_major = pos_parts[0] if len(pos_parts) > 0 else ""
            pos_sub1 = pos_parts[1] if len(pos_parts) > 1 else ""

            # Track character offset for all tokens
            next_char_offset = char_offset + len(surface)

            # Skip non-noun major POS (verbs, adjectives, particles, symbols)
            if pos_major != "名詞":
                char_offset = next_char_offset
                node = node.next
                continue

            # Exclude inappropriate noun subtypes (pronouns, numerals, suffixes, etc.)
            if pos_sub1 in self._SKIP_NOUN_SUBTYPES:
                char_offset = next_char_offset
                node = node.next
                continue

            # Skip pure symbol strings (MeCab may misidentify punctuation as 名詞,サ変接続)
            if not re.search(r'[\w\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', surface):
                char_offset = next_char_offset
                node = node.next
                continue

            # English token filtering: skip stop words and single-char alphanumeric
            if re.match(r'^[A-Za-z0-9_-]+$', surface):
                if surface.lower() in self._ENGLISH_STOP_WORDS or len(surface) <= 1:
                    char_offset = next_char_offset
                    node = node.next
                    continue

            # Single-char rule: allow kanji only, skip hiragana/alphanumeric
            if len(surface) == 1 and not self._KANJI_RE.match(surface):
                char_offset = next_char_offset
                node = node.next
                continue

            key = surface.lower()
            if key not in seen:
                seen.add(key)
                entities.append({
                    "surface": surface,
                    "pos_sub1": pos_sub1,
                    "char_start": char_offset,  # Character offset for adjacency detection
                    "char_end": next_char_offset
                })

            char_offset = next_char_offset
            node = node.next

        return entities

    def _combine_adjacent_nouns(self, entities: list[dict]) -> list[str]:
        """Combine adjacent noun entities based on IPADIC subtype rules.

        Rules (based on AGY review):
          - 固有名詞 + 固有名詞 → combine (e.g., "東京" + "タワー" = "東京タワー")
          - 一般 + 固有名詞 → combine (e.g., "新" + "大阪駅")
          - 固有名詞 + 一般 → combine (e.g., "東京" + "タワー")
          - サ変接続 + 形容動詞語幹 → do NOT combine (e.g., "研究" + "有名")
          - サ変接続 + 一般 → combine (e.g., "人工" + "知能")

        Adjacency is determined by actual character positions (char_start/char_end)
        in the original text, not just list order.

        Returns list of combined noun strings.
        """
        if not entities:
            return []

        # Noun subtypes that can participate in combination (AGY recommendation)
        _COMBINABLE_POS = {"固有名詞", "一般"}

        combined: list[str] = []
        i = 0
        while i < len(entities):
            # Try to extend the combined string with adjacent nouns
            j = i + 1
            while j < len(entities):
                # Check actual text adjacency: entities[j-1].char_end == entities[j].char_start
                prev_entity = entities[j - 1]
                next_entity = entities[j]

                # Adjacency check: char_end of previous must equal char_start of next
                if prev_entity["char_end"] != next_entity["char_start"]:
                    break

                prev_sub1 = prev_entity["pos_sub1"]
                next_sub1 = next_entity["pos_sub1"]

                # Rule 1: Prevent unnatural combinations
                # (e.g., "研究" + "有名" where 研究 is サ変接続 and 有名 is 形容動詞語幹)
                if prev_sub1 == "サ変接続" and next_sub1 == "形容動詞語幹":
                    break
                if prev_sub1 == "形容動詞語幹" or next_sub1 == "形容動詞語幹":
                    break

                # Rule 2: Check if combination is valid based on IPADIC subtypes
                can_combine = (
                    prev_sub1 in _COMBINABLE_POS and next_sub1 in _COMBINABLE_POS
                )

                if can_combine:
                    j += 1
                else:
                    break

            # Build the combined string from entities[i:j]
            if j > i + 1:
                # Multiple adjacent nouns combined
                combined_str = "".join(
                    entities[k]["surface"] for k in range(i, j)
                )
                if len(combined_str) >= 2:  # Minimum 2 characters for meaningful compound
                    combined.append(combined_str)
                i = j  # Skip past the combined entities
            else:
                i += 1

        return combined

    def _extract_entities(self, text: str) -> list[str]:
        """Extract entity candidates from text using MeCab (Japanese) + regex.

        For Japanese text, uses MeCab to extract noun entities. For all text,
        also applies regex rules (capitalized phrases, quoted terms, AKA).

        Returns a deduplicated list preserving first-seen order.
        """
        seen: set[str] = set()
        candidates: list[str] = []

        def _add(name: str) -> None:
            stripped = name.strip()
            if stripped and stripped.lower() not in seen:
                seen.add(stripped.lower())
                candidates.append(stripped)

        # MeCab-based extraction for Japanese text
        if self._JAPANESE_RE.search(text):
            entities = self._parse_japanese_entities(text)
            for entity in entities:
                _add(entity["surface"])

        # Adjacent noun combination (複合名詞結合)
            for combined in self._combine_adjacent_nouns(entities):
                _add(combined)

        # Regex-based extraction (works for all languages)
        for m in _RE_CAPITALIZED.finditer(text):
            _add(m.group(1))

        for m in _RE_DOUBLE_QUOTE.finditer(text):
            _add(m.group(1))

        for m in _RE_SINGLE_QUOTE.finditer(text):
            _add(m.group(1))

        for m in _RE_AKA.finditer(text):
            _add(m.group(1))
            _add(m.group(2))

        return candidates

    def _resolve_entity(self, name: str) -> int:
        """Find an existing entity by name or alias (case-insensitive) or create one.

        Returns the entity_id.
        """
        # Exact name match
        row = self._conn.execute(
            "SELECT entity_id FROM entities WHERE name LIKE ?", (name,)
        ).fetchone()
        if row is not None:
            return int(row["entity_id"])

        # Search aliases — aliases stored as comma-separated; use LIKE with % boundaries
        alias_row = self._conn.execute(
            """
            SELECT entity_id FROM entities
            WHERE ',' || aliases || ',' LIKE '%,' || ? || ',%'
            """,
            (name,),
        ).fetchone()
        if alias_row is not None:
            return int(alias_row["entity_id"])

        # Create new entity
        cur = self._conn.execute(
            "INSERT INTO entities (name) VALUES (?)", (name,)
        )
        self._conn.commit()
        return int(cur.lastrowid)  # type: ignore[return-value]

    def _link_fact_entity(self, fact_id: int, entity_id: int) -> None:
        """Insert into fact_entities, silently ignore if the link already exists."""
        self._conn.execute(
            """
            INSERT OR IGNORE INTO fact_entities (fact_id, entity_id)
            VALUES (?, ?)
            """,
            (fact_id, entity_id),
        )
        self._conn.commit()

    def _compute_hrr_vector(self, fact_id: int, content: str) -> None:
        """Compute and store HRR vector for a fact. No-op when hrr is unavailable."""
        if hrr is None:
            return

        # Get entities linked to this fact
        rows = self._conn.execute(
            """
            SELECT e.name FROM entities e
            JOIN fact_entities fe ON fe.entity_id = e.entity_id
            WHERE fe.fact_id = ?
            """,
            (fact_id,),
        ).fetchall()
        entities = [row["name"] for row in rows]

        vector = hrr.encode_fact(content, entities, self.hrr_dim)
        self._conn.execute(
            "UPDATE facts SET hrr_vector = ? WHERE fact_id = ?",
            (hrr.phases_to_bytes(vector), fact_id),
        )
        self._conn.commit()

    def _rebuild_bank(self, category: str) -> None:
        """Full rebuild of a category's memory bank from all its fact vectors. No-op when hrr is unavailable."""
        if hrr is None:
            return

        bank_name = f"cat:{category}"
        rows = self._conn.execute(
            "SELECT hrr_vector FROM facts WHERE category = ? AND hrr_vector IS NOT NULL",
            (category,),
        ).fetchall()

        if not rows:
            self._conn.execute("DELETE FROM memory_banks WHERE bank_name = ?", (bank_name,))
            self._conn.commit()
            return

        vectors = [hrr.bytes_to_phases(row["hrr_vector"]) for row in rows]
        bank_vector = hrr.bundle(*vectors)
        fact_count = len(vectors)

        # Check SNR
        hrr.snr_estimate(self.hrr_dim, fact_count)

        self._conn.execute(
            """
            INSERT INTO memory_banks (bank_name, vector, dim, fact_count, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(bank_name) DO UPDATE SET
                vector = excluded.vector,
                dim = excluded.dim,
                fact_count = excluded.fact_count,
                updated_at = excluded.updated_at
            """,
            (bank_name, hrr.phases_to_bytes(bank_vector), self.hrr_dim, fact_count),
        )
        self._conn.commit()

    def rebuild_all_vectors(self, dim: int | None = None) -> int:
        """Recompute all HRR vectors + banks from text. For recovery/migration.

        Returns the number of facts processed.
        """
        if hrr is None:
            return 0

        if dim is not None:
            self.hrr_dim = dim

        rows = self._conn.execute(
            "SELECT fact_id, content, category FROM facts"
        ).fetchall()

        categories: set[str] = set()
        for row in rows:
            self._compute_hrr_vector(row["fact_id"], row["content"])
            categories.add(row["category"])

        for category in categories:
            self._rebuild_bank(category)

        return len(rows)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a sqlite3.Row to a plain dict."""
        return dict(row)

    def close(self) -> None:
        """Release this instance's reference to the shared connection.

        The underlying connection is closed only when the last MemoryStore
        referencing the same database is closed, so closing one instance can
        never break sibling instances that still hold it. Idempotent.
        """
        if getattr(self, "_entry", None) is None:
            return
        with MemoryStore._shared_guard:
            entry = self._entry
            if entry is None:
                return
            entry["refs"] -= 1
            if entry["refs"] <= 0:
                try:
                    entry["conn"].close()
                finally:
                    MemoryStore._shared.pop(self._key, None)
            self._entry = None

    def __enter__(self) -> "MemoryStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
