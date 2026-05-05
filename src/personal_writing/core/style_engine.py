"""Style engine — base class and registry for all writing styles."""

import copy
import json
from ..db.repository import StyleRepo


class BaseStyle:
    """Base class for all writing styles."""

    name = ""          # Internal name (e.g., "daily")
    display_name = ""  # Display name (e.g., "日常")
    description = ""   # Description
    config = {}        # Style parameters

    def get_prompt_template(self):
        """Return the prompt template for this style.

        Should be overridden by subclasses.
        """
        raise NotImplementedError

    def get_config(self):
        """Get style configuration with defaults."""
        return self.config

    def post_process(self, content):
        """Post-process generated content."""
        return content.strip()


class DBStyle:
    """Wrapper for DB-based styles (custom styles from skills)."""

    def __init__(self, db_row):
        self.name = db_row["name"]
        self.display_name = db_row["display_name"]
        self.description = db_row.get("description", "")
        self.config = json.loads(db_row["config"]) if isinstance(db_row["config"], str) else db_row.get("config", {})
        self._db_row = db_row

    def get_prompt_template(self):
        return self.config.get("prompt_template", f"你按照{self.display_name}的风格写一篇文章。")

    def get_config(self):
        return self.config

    def post_process(self, content):
        return content.strip()


class StyleRegistry:
    """Registry for all available styles."""

    def __init__(self):
        self._styles = {}

    def register(self, style_class):
        """Register a style class."""
        instance = style_class()
        self._styles[style_class.name] = instance
        return instance

    def get(self, name):
        """Get a style by name."""
        base_style = self._styles.get(name)
        if base_style:
            # Return a fresh shallow copy so DB prompt/config overrides for one
            # request never mutate the registered singleton or leak into later
            # style calls.
            style = copy.copy(base_style)
            style.config = dict(getattr(base_style.__class__, "config", {}) or {})
            # For built-in styles, overlay DB config if available
            db_row = StyleRepo.get_by_name(name)
            if db_row:
                db_config = json.loads(db_row["config"]) if isinstance(db_row["config"], str) else db_row.get("config", {})
                # Override display_name, description from DB
                style.display_name = db_row.get("display_name", style.display_name)
                style.description = db_row.get("description", style.description)
                # Merge config (DB values take precedence)
                merged = dict(style.config)
                merged.update(db_config)
                style.config = merged
            return style
        # Try DB (custom styles from uploaded skills)
        db_style = StyleRepo.get_by_name(name)
        if db_style:
            return DBStyle(db_style)
        return None

    def reload(self):
        """Refresh hook for DB-backed edits.

        Built-in styles read DB overrides on every get/list call, and custom
        styles are loaded directly from the DB, so there is no in-memory cache
        to rebuild here.
        """
        return None

    def list(self):
        """List all registered styles."""
        return list(self._styles.values())

    def list_info(self):
        """List all style info for display."""
        styles = []
        for s in self._styles.values():
            # Check DB for user-overridden values
            db_row = StyleRepo.get_by_name(s.name)
            base_config = dict(getattr(s.__class__, "config", {}) or {})
            config = base_config
            if db_row:
                db_config = json.loads(db_row["config"]) if isinstance(db_row["config"], str) else db_row.get("config", {})
                config.update(db_config)
            category = config.get("category") or ("academic" if s.name == "zheng_ge_academic" else "general")
            styles.append({
                "name": s.name,
                "display_name": db_row["display_name"] if db_row else s.display_name,
                "description": db_row["description"] if db_row else s.description,
                "config": config,
                "category": category,
                "is_builtin": True,
            })
        # Also include DB custom styles
        for db_style in StyleRepo.list():
            if db_style["name"] not in self._styles:
                config = json.loads(db_style["config"]) if isinstance(db_style["config"], str) else db_style.get("config", {})
                category = config.get("category") or "custom"
                styles.append({
                    "name": db_style["name"],
                    "display_name": db_style["display_name"],
                    "description": db_style["description"],
                    "config": config,
                    "category": category,
                    "is_builtin": bool(db_style.get("is_builtin", 0)),
                })
        return styles


# Global registry
registry = StyleRegistry()
