"""Memory utilization layer — user-facing convenience functions.

Wraps the low-level MemoryStore API into high-level operations
for real-world usage: preference registration, recommendation, and feedback.

Usage from agent code:
    from plugins.memory_util.utilization import (
        register_preference, recommend_by_category, record_reaction, get_all_preferences
    )

Author: ely (Hermes Agent)
Date: 2026-08-03
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_store():
    """Get the MemoryStore instance from config.

    Loads db_path and default_trust from config.yaml directly,
    without depending on the holographic plugin.
    """
    try:
        from hermes_constants import get_hermes_home
        config_path = get_hermes_home() / "config.yaml"
        if not config_path.exists():
            db_path = get_hermes_home() / "memory" / "fact.db"
        else:
            import yaml
            with open(config_path, encoding="utf-8-sig") as f:
                all_config = yaml.safe_load(f) or {}
            plugins = all_config.get("plugins", {}) or {}
            mu_config = plugins.get("memory_util") or {}
            db_path_str = mu_config.get("db_path")
            if db_path_str:
                db_path = Path(db_path_str).expanduser()
            else:
                db_path = get_hermes_home() / "memory" / "fact.db"
    except Exception:
        db_path = Path.home() / ".hermes" / "memory" / "fact.db"

    default_trust = 0.5
    try:
        from hermes_constants import get_hermes_home
        config_path = get_hermes_home() / "config.yaml"
        if config_path.exists():
            import yaml
            with open(config_path, encoding="utf-8-sig") as f:
                all_config = yaml.safe_load(f) or {}
            plugins = all_config.get("plugins", {}) or {}
            mu_config = plugins.get("memory_util") or {}
            default_trust = float(mu_config.get("default_trust", 0.5))
    except Exception:
        pass

    # Import with fallback for direct execution vs. plugin context
    try:
        from .store import MemoryStore
    except ImportError:
        from store import MemoryStore

    store = MemoryStore(
        db_path=str(db_path),
        default_trust=default_trust,
    )
    return store


def register_preference(content: str, category: str = "general", tags: str = "") -> int:
    """Register a user preference or fact.

    Args:
        content: The fact content (e.g., "トミの好きな音楽ジャンルはジャズ。")
        category: Category name in English (e.g., "music", "movie", "food", "hobby")
        tags: Comma-separated tags (e.g., "jazz,blue,vinyl")

    Returns:
        fact_id (int): The ID of the newly created fact.

    Example:
        >>> fid = register_preference("トミの好きな音楽ジャンルはジャズ。", "music")
        >>> fid  # e.g., 21
    """
    store = _get_store()
    try:
        fact_id = store.add_fact(content, category=category, tags=tags)
        logger.info("Registered preference: [%d] %s (category=%s)", fact_id, content[:50], category)
        return fact_id
    except Exception as e:
        logger.error("Failed to register preference: %s", e)
        raise


def recommend_by_category(category: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Get recommendations filtered by category.

    Returns facts sorted by trust_score (descending) within the specified category.
    Useful for recommendation scenarios like "what music should I listen to?".

    Args:
        category: Category name in English (e.g., "music", "movie")
        limit: Maximum number of results to return.

    Returns:
        List of fact dicts with keys: content, category, tags, trust_score

    Example:
        >>> recs = recommend_by_category("music")
        >>> for r in recs:
        ...     print(f"[{r['trust_score']:.2f}] {r['content']}")
    """
    store = _get_store()
    try:
        facts = store.list_facts(category=category, min_trust=0.0, limit=limit)
        return facts
    except Exception as e:
        logger.error("Failed to get recommendations for category '%s': %s", category, e)
        return []


def record_reaction(fact_id: int, helpful: bool = True) -> Dict[str, Any]:
    """Record user feedback on a fact (helpful or unhelpful).

    This adjusts the trust_score of the fact. Helpful feedback increases
    trust; unhelpful feedback decreases it. Facts with trust below the
    minimum threshold are filtered from search results.

    Args:
        fact_id: The ID of the fact to rate.
        helpful: True for "helpful" (いいね), False for "unhelpful" (違うな).

    Returns:
        Dict with 'success' (bool) and optionally 'new_trust_score'.

    Example:
        >>> record_reaction(17, helpful=True)  # User liked this recommendation
    """
    store = _get_store()
    try:
        result = store.record_feedback(fact_id, helpful=helpful)
        if result.get("success"):
            logger.info(
                "Recorded feedback for fact [%d]: %s (new_trust=%.2f)",
                fact_id,
                "helpful" if helpful else "unhelpful",
                result.get("new_trust_score", 0),
            )
        return result
    except KeyError:
        logger.warning("record_reaction called with invalid fact_id=%d", fact_id)
        return {"success": False, "error": f"fact_id {fact_id} not found"}
    except Exception as e:
        logger.error("Failed to record reaction for fact [%d]: %s", fact_id, e)
        return {"success": False, "error": str(e)}


def get_all_preferences() -> List[Dict[str, Any]]:
    """Get all registered facts (for debugging/backup).

    Returns all facts sorted by trust_score (descending), regardless of category.
    This is the full dump — use with caution in production.

    Returns:
        List of all fact dicts sorted by trust_score descending.

    Example:
        >>> all_facts = get_all_preferences()
        >>> print(f"Total: {len(all_facts)} facts")
    """
    store = _get_store()
    try:
        return store.list_facts(category=None, min_trust=0.0, limit=1000)
    except Exception as e:
        logger.error("Failed to get all preferences: %s", e)
        return []


def search_facts(query: str, category: Optional[str] = None) -> List[Dict[str, Any]]:
    """Search facts by keyword query.

    Uses FTS5 trigram indexing for English keywords (3+ chars) and
    LIKE fallback for Japanese/shorter queries.

    Args:
        query: Search keyword (e.g., "寿司", "AI", "Python")
        category: Optional category filter.

    Returns:
        List of matching fact dicts sorted by relevance.

    Example:
        >>> results = search_facts("寿司")
        >>> for r in results:
        ...     print(f"[{r['fact_id']}] {r['content']}")
    """
    store = _get_store()
    try:
        return store.search_facts(query, category=category)
    except Exception as e:
        logger.error("Failed to search facts for '%s': %s", query, e)
        return []


def update_fact_content(fact_id: int, new_content: str) -> bool:
    """Update the content of an existing fact.

    Args:
        fact_id: The ID of the fact to update.
        new_content: The new content string.

    Returns:
        True if updated successfully, False otherwise.

    Example:
        >>> update_fact_content(18, "トミの好きな映画ジャンルはサイエンスフィクション。")
    """
    store = _get_store()
    try:
        return store.update_fact(fact_id, content=new_content)
    except Exception as e:
        logger.error("Failed to update fact [%d]: %s", fact_id, e)
        return False


def remove_fact(fact_id: int) -> bool:
    """Remove a fact from the store.

    Args:
        fact_id: The ID of the fact to remove.

    Returns:
        True if removed successfully, False otherwise.

    Example:
        >>> remove_fact(99999)  # Non-existent ID returns False gracefully
    """
    store = _get_store()
    try:
        return store.remove_fact(fact_id)
    except Exception as e:
        logger.error("Failed to remove fact [%d]: %s", fact_id, e)
        return False
