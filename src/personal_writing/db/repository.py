"""Database CRUD operations."""

import json
from .schema import get_connection
from ..utils.text_stats import count_text_units


class MaterialRepo:
    """CRUD for materials table."""

    @staticmethod
    def create(title="", source_type="paste", raw_content="", content_type="general"):
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO materials (title, source_type, raw_content, content_type) VALUES (?, ?, ?, ?)",
            (title, source_type, raw_content, content_type),
        )
        material_id = cur.lastrowid
        conn.commit()
        conn.close()
        return material_id

    @staticmethod
    def get(material_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list(limit=20, offset=0):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM materials ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update_status(material_id, status):
        conn = get_connection()
        conn.execute(
            "UPDATE materials SET status = ?, updated_at = datetime('now', 'localtime') WHERE id = ?",
            (status, material_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def delete(material_id):
        """Delete material and cascade sessions/articles."""
        conn = get_connection()
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def search(query, limit=30):
        """Search materials by content or title."""
        conn = get_connection()
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT * FROM materials WHERE raw_content LIKE ? OR title LIKE ? ORDER BY created_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class SessionRepo:
    """CRUD for sessions table."""

    @staticmethod
    def create(material_id, style_names, prompt="", headline_formula=""):
        conn = get_connection()
        style_json = json.dumps(style_names, ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO sessions (material_id, prompt, style_names, headline_formula) VALUES (?, ?, ?, ?)",
            (material_id, prompt, style_json, headline_formula),
        )
        session_id = cur.lastrowid
        conn.commit()
        conn.close()
        return session_id

    @staticmethod
    def get(session_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_by_material(material_id):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM sessions WHERE material_id = ? ORDER BY created_at DESC",
            (material_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def list_recent(limit=12):
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT
                s.*,
                m.title AS material_title,
                m.raw_content AS material_content
            FROM sessions s
            LEFT JOIN materials m ON m.id = s.material_id
            ORDER BY s.created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update_title(session_id, title):
        conn = get_connection()
        conn.execute("UPDATE sessions SET title = ? WHERE id = ?", (title, session_id))
        conn.commit()
        conn.close()

    @staticmethod
    def delete(session_id):
        conn = get_connection()
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_with_material(session_id):
        """Delete a session and its source material.

        Deleting the material cascades to all sessions/articles that were
        generated from the same upload/paste, keeping the material library in
        sync with the sidebar task list.
        """
        conn = get_connection()
        row = conn.execute("SELECT material_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            conn.close()
            return False
        conn.execute("DELETE FROM materials WHERE id = ?", (row["material_id"],))
        conn.commit()
        conn.close()
        return True


class ArticleRepo:
    """CRUD for articles table."""

    @staticmethod
    def create(session_id, style, title="", content="", headline_formula=""):
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO articles (session_id, style, title, original_title, content, original_content, headline_formula) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, style, title, title, content, content, headline_formula),
        )
        article_id = cur.lastrowid
        conn.commit()
        conn.close()
        return article_id

    @staticmethod
    def get(article_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_by_session(session_id):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM articles WHERE session_id = ? ORDER BY id",
            (session_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def save_headline_candidates(article_id, candidates):
        """Save headline candidates (list of strings) as JSON."""
        conn = get_connection()
        conn.execute(
            "UPDATE articles SET headline_candidates = ? WHERE id = ?",
            (json.dumps(candidates, ensure_ascii=False), article_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def select_headline(article_id, headline):
        """Record the user's selected headline."""
        conn = get_connection()
        if headline:
            conn.execute(
                "UPDATE articles SET headline_selected = ?, title = ? WHERE id = ?",
                (headline, headline, article_id),
            )
        else:
            conn.execute(
                """
                UPDATE articles
                SET headline_selected = '',
                    title = COALESCE(NULLIF(original_title, ''), title)
                WHERE id = ?
                """,
                (article_id,),
            )
        conn.commit()
        conn.close()

    @staticmethod
    def set_output_path(article_id, path):
        """Set the local file output path for an article."""
        conn = get_connection()
        conn.execute(
            "UPDATE articles SET output_path = ? WHERE id = ?",
            (path, article_id),
        )
        conn.commit()
        conn.close()


class StyleRepo:
    """CRUD for styles table."""

    @staticmethod
    def list():
        conn = get_connection()
        rows = conn.execute("SELECT * FROM styles ORDER BY is_builtin DESC, id").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_by_name(name):
        conn = get_connection()
        row = conn.execute("SELECT * FROM styles WHERE name = ?", (name,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def create(name, display_name, description="", config=None, is_builtin=0):
        conn = get_connection()
        config_str = json.dumps(config or {}, ensure_ascii=False)
        cur = conn.execute(
            "INSERT INTO styles (name, display_name, description, config, is_builtin) VALUES (?, ?, ?, ?, ?)",
            (name, display_name, description, config_str, is_builtin),
        )
        style_id = cur.lastrowid
        conn.commit()
        conn.close()
        return style_id


class HeadlineFeedbackRepo:
    """CRUD for headline_feedback table."""

    @staticmethod
    def record(article_id, headline, formula_name="", was_selected=0, is_custom=0, material_id=0, style=""):
        conn = get_connection()
        conn.execute(
            "INSERT INTO headline_feedback (article_id, material_id, style, headline, formula_name, was_selected, is_custom) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (article_id, material_id, style, headline, formula_name, was_selected, is_custom),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_preferred_formulas(style=None, limit=5):
        """Get most frequently selected headline formulas for a style."""
        conn = get_connection()
        if style:
            rows = conn.execute(
                """SELECT formula_name, COUNT(*) as cnt FROM headline_feedback
                   WHERE was_selected = 1 AND formula_name != '' AND style = ?
                   GROUP BY formula_name ORDER BY cnt DESC LIMIT ?""",
                (style, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT formula_name, COUNT(*) as cnt FROM headline_feedback
                   WHERE was_selected = 1 AND formula_name != ''
                   GROUP BY formula_name ORDER BY cnt DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_history(limit=20):
        """Get recent headline selections."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT * FROM headline_feedback ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class StatsRepo:
    """Statistics queries."""

    @staticmethod
    def articles_by_style():
        conn = get_connection()
        rows = conn.execute(
            "SELECT style, COUNT(*) as count FROM articles GROUP BY style ORDER BY count DESC"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def total_counts():
        conn = get_connection()
        materials = conn.execute("SELECT COUNT(*) as c FROM materials").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) as c FROM sessions").fetchone()[0]
        articles = conn.execute("SELECT COUNT(*) as c FROM articles").fetchone()[0]
        contents = conn.execute("SELECT content FROM articles").fetchall()
        total_words = sum(count_text_units(row["content"]) for row in contents)
        conn.close()
        return {"materials": materials, "sessions": sessions, "articles": articles, "total_words": total_words}

    @staticmethod
    def articles_by_day(limit=14):
        conn = get_connection()
        rows = conn.execute(
            """SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) as count
               FROM articles GROUP BY day ORDER BY day DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return list(reversed([dict(r) for r in rows]))


class CommonPhraseRepo:
    """CRUD for common_phrases table."""

    @staticmethod
    def create(phrase, category=""):
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO common_phrases (phrase, category) VALUES (?, ?)",
            (phrase, category),
        )
        phrase_id = cur.lastrowid
        conn.commit()
        conn.close()
        return phrase_id

    @staticmethod
    def list(category=None):
        conn = get_connection()
        if category:
            rows = conn.execute(
                "SELECT * FROM common_phrases WHERE category = ? ORDER BY id DESC",
                (category,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM common_phrases ORDER BY category, id DESC"
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete(phrase_id):
        conn = get_connection()
        conn.execute("DELETE FROM common_phrases WHERE id = ?", (phrase_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def update(phrase_id, phrase, category=""):
        conn = get_connection()
        conn.execute(
            "UPDATE common_phrases SET phrase = ?, category = ? WHERE id = ?",
            (phrase, category, phrase_id),
        )
        conn.commit()
        conn.close()


class StyleExampleRepo:
    """CRUD for style_examples table."""

    @staticmethod
    def list_by_style(style_id):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM style_examples WHERE style_id = ? ORDER BY id DESC",
            (style_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def create(style_id, title="", content="", source=""):
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO style_examples (style_id, title, content, source) VALUES (?, ?, ?, ?)",
            (style_id, title, content, source),
        )
        ex_id = cur.lastrowid
        conn.commit()
        conn.close()
        return ex_id

    @staticmethod
    def delete(example_id):
        conn = get_connection()
        conn.execute("DELETE FROM style_examples WHERE id = ?", (example_id,))
        conn.commit()
        conn.close()


class ReviewAnalysisRepo:
    """CRUD for review_analysis table (persistent AI writing analysis)."""

    @staticmethod
    def save(analysis, article_count):
        conn = get_connection()
        conn.execute(
            "INSERT INTO review_analysis (analysis, article_count) VALUES (?, ?)",
            (analysis, article_count),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def get_latest(limit=5):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM review_analysis ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class HeadlineFormulaRepo:
    """CRUD for headline_formulas table."""

    @staticmethod
    def list_by_style(style_name):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM headline_formulas WHERE suitable_styles LIKE ? AND is_active = 1",
            (f"%{style_name}%",),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def list_all():
        conn = get_connection()
        rows = conn.execute("SELECT * FROM headline_formulas WHERE is_active = 1").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def create(name, template, suitable_styles, description="", example=""):
        conn = get_connection()
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO headline_formulas
                   (name, template, suitable_styles, description, example, is_active)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (name, template, suitable_styles, description, example),
            )
            inserted = cur.rowcount > 0
            conn.commit()
        except Exception:
            inserted = False
        conn.close()
        return inserted


class HeadlineLibraryRepo:
    """CRUD for user-collected headline examples."""

    @staticmethod
    def create(headline, style="", note="", source=""):
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO headline_library (headline, style, note, source) VALUES (?, ?, ?, ?)",
            (headline, style, note, source),
        )
        item_id = cur.lastrowid
        conn.commit()
        conn.close()
        return item_id

    @staticmethod
    def list(style="", limit=30):
        conn = get_connection()
        if style:
            rows = conn.execute(
                """
                SELECT * FROM headline_library
                WHERE style = ? OR style = ''
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (style, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM headline_library ORDER BY created_at DESC, id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete(item_id):
        conn = get_connection()
        conn.execute("DELETE FROM headline_library WHERE id = ?", (item_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def delete_batch(item_ids):
        """Delete multiple headline library items by ids."""
        conn = get_connection()
        placeholders = ",".join("?" * len(item_ids))
        conn.execute(f"DELETE FROM headline_library WHERE id IN ({placeholders})", item_ids)
        conn.commit()
        conn.close()

    @staticmethod
    def _get(item_id):
        """Get a single headline library item by id."""
        conn = get_connection()
        row = conn.execute("SELECT * FROM headline_library WHERE id = ?", (item_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(item_id, headline=None, style=None, note=None, source=None):
        conn = get_connection()
        updates = []
        params = []
        if headline is not None:
            updates.append("headline = ?")
            params.append(headline)
        if style is not None:
            updates.append("style = ?")
            params.append(style)
        if note is not None:
            updates.append("note = ?")
            params.append(note)
        if source is not None:
            updates.append("source = ?")
            params.append(source)
        if updates:
            params.append(item_id)
            conn.execute(f"UPDATE headline_library SET {', '.join(updates)} WHERE id = ?", tuple(params))
            conn.commit()
        conn.close()


class HeadlineAnalysisRepo:
    """CRUD for headline_analysis table (AI analysis of collected headlines)."""

    @staticmethod
    def create(style, headline_ids, headline_count, summary, patterns, key_takeaways, tips, raw_analysis):
        conn = get_connection()
        cur = conn.execute(
            """INSERT INTO headline_analysis (style, headline_ids, headline_count, summary, patterns, key_takeaways, tips, raw_analysis)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (style, json.dumps(headline_ids), headline_count, summary,
             json.dumps(patterns, ensure_ascii=False),
             json.dumps(key_takeaways, ensure_ascii=False), tips, raw_analysis),
        )
        analysis_id = cur.lastrowid
        conn.commit()
        conn.close()
        return analysis_id

    @staticmethod
    def list(limit=10):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM headline_analysis ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get(analysis_id):
        conn = get_connection()
        row = conn.execute(
            "SELECT * FROM headline_analysis WHERE id = ?",
            (analysis_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def delete(analysis_id):
        conn = get_connection()
        conn.execute("DELETE FROM headline_analysis WHERE id = ?", (analysis_id,))
        conn.commit()
        conn.close()


class HeadlineGenerationRepo:
    """CRUD for headline_generation_history table."""

    @staticmethod
    def create(content_hash, content_preview, style, result_json):
        conn = get_connection()
        cur = conn.execute(
            "INSERT INTO headline_generation_history (content_hash, content_preview, style, result) VALUES (?, ?, ?, ?)",
            (content_hash, content_preview, style, result_json),
        )
        gen_id = cur.lastrowid
        conn.commit()
        conn.close()
        return gen_id

    @staticmethod
    def list_by_content_hash(content_hash, limit=5):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM headline_generation_history WHERE content_hash = ? ORDER BY created_at DESC LIMIT ?",
            (content_hash, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def list_recent(limit=10):
        """List recent distinct generations (grouped by content_hash)."""
        conn = get_connection()
        rows = conn.execute(
            """SELECT h.* FROM headline_generation_history h
               INNER JOIN (
                   SELECT content_hash, MAX(created_at) AS max_ct
                   FROM headline_generation_history
                   GROUP BY content_hash
               ) g ON h.content_hash = g.content_hash AND h.created_at = g.max_ct
               ORDER BY h.created_at DESC
               LIMIT ?""",
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
