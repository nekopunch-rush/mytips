"""memory_util — customized memory plugin using MemoryProvider interface.

Registers as a MemoryProvider plugin, providing structured fact storage
with entity resolution, trust scoring, and FTS5-based retrieval.

Based on holographic plugin by dusterbloom (PR #2351), adapted for
local fact management with utilization tools.

Config in $HERMES_HOME/config.yaml (profile-scoped):
  plugins:
    memory_util:
      db_path: $HERMES_HOME/memory/fact.db   # omit to use the default
      auto_extract: false
      default_trust: 0.5
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List


logger = logging.getLogger(__name__)


class MemoryUtilProvider:
    """Customized memory provider using holographic's store/retrieval."""

    name = "memory_util"
    description = (
        "Structured fact storage with entity resolution, trust scoring, "
        "and FTS5-based retrieval."
    )

    def __init__(self, all_config: Dict[str, Any]) -> None:
        # all_config is already the memory_util section (from _load_plugin_config)
        self._config = all_config or {}
        db_path = self._config.get("db_path")
        if not db_path:
            raise ValueError(
                "memory_util plugin requires 'db_path' in config. "
                "Add: plugins.memory_util.db_path"
            )

        from .store import MemoryStore
        from .retrieval import FactRetriever

        self._store = MemoryStore(db_path)
        self._retriever = FactRetriever(self._store)

    def register_tools(self, ctx: Any) -> None:
        """Register memory_util tools with the agent."""
        from .utilization import register_utilization_tools
        register_utilization_tools(ctx, self._store)

    def on_session_end(self, ctx: Any) -> None:
        """Called when a session ends."""
        pass

    def __repr__(self) -> str:
        return f"MemoryUtilProvider(db_path={self._store.db_path})"


def register(ctx: Any) -> None:
    """Called by the memory plugin discovery system."""
    try:
        # Load config directly from config.yaml (matching holographic pattern)
        all_config = _load_plugin_config()
        provider = MemoryUtilProvider(all_config)
        ctx.register_memory_provider(provider)
        logger.info(f"memory_util plugin registered (db_path={provider._store.db_path})")
    except Exception as e:
        logger.warning(f"Failed to register memory_util plugin: {e}")


def _load_plugin_config() -> dict:
    """Load config from config.yaml (matching holographic pattern)."""
    try:
        from hermes_constants import get_hermes_home
        config_path = get_hermes_home() / "config.yaml"
        if not config_path.exists():
            return {}
        import yaml
        with open(config_path, encoding="utf-8-sig") as f:
            all_config = yaml.safe_load(f) or {}
        # Direct dict access instead of cfg_get
        plugins = all_config.get("plugins", {}) or {}
        return plugins.get("memory_util") or {}
    except Exception:
        return {}


def register_utilization_tools(ctx: Any, store) -> None:
    """Register all memory_util tools with the agent context."""
    from .utilization import (
        register_preference,
        recommend_by_category,
        record_reaction,
        get_all_preferences,
        search_facts,
        update_fact_content,
        remove_fact,
    )

    ctx.register_tool(
        "memory_util_store",
        register_preference,
        description="Register a new fact/preference to the memory store.",
    )
    ctx.register_tool(
        "memory_util_recommend",
        recommend_by_category,
        description="Recommend facts by category (sorted by trust_score).",
    )
    ctx.register_tool(
        "memory_util_feedback",
        record_reaction,
        description="Record user feedback on a fact (helpful/unhelpful).",
    )
    ctx.register_tool(
        "memory_util_list",
        get_all_preferences,
        description="List all facts in the memory store.",
    )
    ctx.register_tool(
        "memory_util_search",
        search_facts,
        description="Search facts by keyword (FTS5 trigram + LIKE fallback).",
    )
    ctx.register_tool(
        "memory_util_update",
        update_fact_content,
        description="Update the content of an existing fact.",
    )
    ctx.register_tool(
        "memory_util_remove",
        remove_fact,
        description="Remove a fact by ID.",
    )
