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
    def create(material_id, style_names, prompt="", headline_formula="", library_ids=None, retrieval_policy=None):
        conn = get_connection()
        style_json = json.dumps(style_names, ensure_ascii=False)
        library_json = json.dumps(library_ids or [], ensure_ascii=False)
        policy_json = json.dumps(retrieval_policy or {}, ensure_ascii=False)
        cur = conn.execute(
            """
            INSERT INTO sessions (material_id, prompt, style_names, headline_formula, library_ids, retrieval_policy)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (material_id, prompt, style_json, headline_formula, library_json, policy_json),
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
    def set_retrieval_snapshot(session_id, snapshot_id):
        conn = get_connection()
        conn.execute("UPDATE sessions SET retrieval_snapshot_id = ? WHERE id = ?", (snapshot_id, session_id))
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
            "INSERT INTO articles (session_id, style, title, content, original_content, headline_formula) VALUES (?, ?, ?, ?, ?, ?)",
            (session_id, style, title, content, content, headline_formula),
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
        conn.execute(
            "UPDATE articles SET headline_selected = ?, title = ? WHERE id = ?",
            (headline, headline, article_id),
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

    @staticmethod
    def set_grounding(article_id, citation_summary=None, grounding_status=""):
        conn = get_connection()
        conn.execute(
            "UPDATE articles SET citation_summary = ?, grounding_status = ? WHERE id = ?",
            (json.dumps(citation_summary or {}, ensure_ascii=False), grounding_status, article_id),
        )
        conn.commit()
        conn.close()


class MaterialLibraryRepo:
    """CRUD for material_libraries."""

    @staticmethod
    def create(name, description="", topic="", discipline="", citation_style="inline_source_id", strict_grounding=1):
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO material_libraries
            (name, description, topic, discipline, citation_style, strict_grounding)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, description, topic, discipline, citation_style, int(bool(strict_grounding))),
        )
        library_id = cur.lastrowid
        conn.commit()
        conn.close()
        return library_id

    @staticmethod
    def get(library_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM material_libraries WHERE id = ?", (library_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list(limit=100):
        conn = get_connection()
        rows = conn.execute(
            """
            SELECT
                l.*,
                COUNT(d.id) AS document_count,
                SUM(CASE WHEN d.parse_status = 'ready' THEN 1 ELSE 0 END) AS ready_count,
                SUM(CASE WHEN d.parse_status = 'failed' THEN 1 ELSE 0 END) AS failed_count
            FROM material_libraries l
            LEFT JOIN library_documents d ON d.library_id = l.id
            GROUP BY l.id
            ORDER BY l.updated_at DESC, l.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def touch(library_id):
        conn = get_connection()
        conn.execute(
            "UPDATE material_libraries SET updated_at = datetime('now', 'localtime') WHERE id = ?",
            (library_id,),
        )
        conn.commit()
        conn.close()


class MaterialFolderRepo:
    """CRUD for material-library folders/categories."""

    @staticmethod
    def create(library_id, name, parent_id=None, description="", sort_order=0):
        conn = get_connection()
        parent_id = int(parent_id) if parent_id not in (None, "", 0, "0") else None
        if parent_id:
            parent = conn.execute(
                "SELECT id FROM material_library_folders WHERE id = ? AND library_id = ?",
                (parent_id, library_id),
            ).fetchone()
            if not parent:
                conn.close()
                raise ValueError("父级文件夹不属于当前素材库")
        cur = conn.execute(
            """
            INSERT INTO material_library_folders
            (library_id, parent_id, name, description, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (library_id, parent_id, name, description, int(sort_order or 0)),
        )
        folder_id = cur.lastrowid
        conn.commit()
        conn.close()
        MaterialLibraryRepo.touch(library_id)
        return folder_id

    @staticmethod
    def get(folder_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM material_library_folders WHERE id = ?", (folder_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def update(folder_id, name=None, description=None, parent_id=None, sort_order=None):
        conn = get_connection()
        current = conn.execute("SELECT * FROM material_library_folders WHERE id = ?", (folder_id,)).fetchone()
        if not current:
            conn.close()
            return False
        next_parent = current["parent_id"]
        if parent_id is not None:
            next_parent = int(parent_id) if parent_id not in ("", 0, "0") else None
            if next_parent == folder_id:
                conn.close()
                raise ValueError("文件夹不能作为自己的父级")
            if next_parent:
                parent = conn.execute(
                    "SELECT id FROM material_library_folders WHERE id = ? AND library_id = ?",
                    (next_parent, current["library_id"]),
                ).fetchone()
                if not parent:
                    conn.close()
                    raise ValueError("父级文件夹不属于当前素材库")
        conn.execute(
            """
            UPDATE material_library_folders
            SET name = ?, description = ?, parent_id = ?, sort_order = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (
                current["name"] if name is None else name,
                current["description"] if description is None else description,
                next_parent,
                current["sort_order"] if sort_order is None else int(sort_order or 0),
                folder_id,
            ),
        )
        conn.commit()
        conn.close()
        MaterialLibraryRepo.touch(current["library_id"])
        return True

    @staticmethod
    def list_by_library(library_id, include_counts=True):
        conn = get_connection()
        if include_counts:
            rows = conn.execute(
                """
                SELECT
                    f.*,
                    COUNT(d.id) AS document_count,
                    SUM(CASE WHEN d.parse_status = 'ready' THEN 1 ELSE 0 END) AS ready_count
                FROM material_library_folders f
                LEFT JOIN library_documents d ON d.folder_id = f.id
                WHERE f.library_id = ?
                GROUP BY f.id
                ORDER BY f.parent_id IS NOT NULL, f.sort_order, f.name, f.id
                """,
                (library_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM material_library_folders
                WHERE library_id = ?
                ORDER BY parent_id IS NOT NULL, sort_order, name, id
                """,
                (library_id,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def tree_by_library(library_id):
        folders = MaterialFolderRepo.list_by_library(library_id)
        by_parent = {}
        for folder in folders:
            folder["children"] = []
            by_parent.setdefault(folder.get("parent_id"), []).append(folder)
        for folder in folders:
            folder["children"] = by_parent.get(folder["id"], [])
        return by_parent.get(None, [])

    @staticmethod
    def descendant_ids(library_id, folder_id):
        folder_id = int(folder_id)
        conn = get_connection()
        rows = conn.execute(
            """
            WITH RECURSIVE folder_tree(id) AS (
                SELECT id FROM material_library_folders
                WHERE id = ? AND library_id = ?
                UNION ALL
                SELECT f.id FROM material_library_folders f
                JOIN folder_tree ft ON f.parent_id = ft.id
                WHERE f.library_id = ?
            )
            SELECT id FROM folder_tree
            """,
            (folder_id, library_id, library_id),
        ).fetchall()
        conn.close()
        return [int(r["id"]) for r in rows]


class LibraryDocumentRepo:
    """CRUD for library_documents."""

    @staticmethod
    def create(
        library_id,
        title="",
        original_filename="",
        file_path="",
        source_type="paste",
        source_url="",
        mime_type="",
        sha256="",
        folder_id=None,
        tags=None,
    ):
        conn = get_connection()
        folder_id = int(folder_id) if folder_id not in (None, "", 0, "0") else None
        if folder_id:
            folder = conn.execute(
                "SELECT id FROM material_library_folders WHERE id = ? AND library_id = ?",
                (folder_id, library_id),
            ).fetchone()
            if not folder:
                conn.close()
                raise ValueError("文件夹不属于当前素材库")
        cur = conn.execute(
            """
            INSERT INTO library_documents
            (library_id, folder_id, title, original_filename, file_path, source_type, source_url, mime_type, sha256, parse_status, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)
            """,
            (
                library_id,
                folder_id,
                title,
                original_filename,
                file_path,
                source_type,
                source_url,
                mime_type,
                sha256,
                json.dumps(tags or [], ensure_ascii=False),
            ),
        )
        document_id = cur.lastrowid
        conn.commit()
        conn.close()
        MaterialLibraryRepo.touch(library_id)
        return document_id

    @staticmethod
    def get(document_id):
        conn = get_connection()
        row = conn.execute(
            """
            SELECT d.*, l.name AS library_name, f.name AS folder_name
            FROM library_documents d
            LEFT JOIN material_libraries l ON l.id = d.library_id
            LEFT JOIN material_library_folders f ON f.id = d.folder_id
            WHERE d.id = ?
            """,
            (document_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    @staticmethod
    def list_by_library(library_id, folder_id=None):
        conn = get_connection()
        if folder_id == "uncategorized":
            rows = conn.execute(
                """
                SELECT d.*, f.name AS folder_name
                FROM library_documents d
                LEFT JOIN material_library_folders f ON f.id = d.folder_id
                WHERE d.library_id = ? AND d.folder_id IS NULL
                ORDER BY d.created_at DESC, d.id DESC
                """,
                (library_id,),
            ).fetchall()
        elif folder_id not in (None, "", 0, "0"):
            folder_ids = MaterialFolderRepo.descendant_ids(library_id, folder_id)
            if not folder_ids:
                conn.close()
                return []
            placeholders = ",".join("?" for _ in folder_ids)
            rows = conn.execute(
                f"""
                SELECT d.*, f.name AS folder_name
                FROM library_documents d
                LEFT JOIN material_library_folders f ON f.id = d.folder_id
                WHERE d.library_id = ? AND d.folder_id IN ({placeholders})
                ORDER BY d.created_at DESC, d.id DESC
                """,
                (library_id, *folder_ids),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT d.*, f.name AS folder_name
                FROM library_documents d
                LEFT JOIN material_library_folders f ON f.id = d.folder_id
                WHERE d.library_id = ?
                ORDER BY d.created_at DESC, d.id DESC
                """,
                (library_id,),
            ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def update_parse_result(document_id, status, page_count=0, word_count=0, text_preview="", parse_error="", title=None):
        conn = get_connection()
        row = conn.execute("SELECT library_id FROM library_documents WHERE id = ?", (document_id,)).fetchone()
        if title is None:
            conn.execute(
                """
                UPDATE library_documents
                SET parse_status = ?, page_count = ?, word_count = ?, text_preview = ?, parse_error = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (status, page_count, word_count, text_preview, parse_error, document_id),
            )
        else:
            conn.execute(
                """
                UPDATE library_documents
                SET title = ?, parse_status = ?, page_count = ?, word_count = ?, text_preview = ?, parse_error = ?,
                    updated_at = datetime('now', 'localtime')
                WHERE id = ?
                """,
                (title, status, page_count, word_count, text_preview, parse_error, document_id),
            )
        conn.commit()
        conn.close()
        if row:
            MaterialLibraryRepo.touch(row["library_id"])

    @staticmethod
    def update_reference_metadata(document_id, metadata):
        """Attach Zotero-style bibliographic metadata to one document."""
        metadata = metadata or {}
        authors = metadata.get("authors") or []
        tags = metadata.get("tags") or []
        conn = get_connection()
        row = conn.execute("SELECT library_id FROM library_documents WHERE id = ?", (document_id,)).fetchone()
        conn.execute(
            """
            UPDATE library_documents
            SET title = COALESCE(NULLIF(?, ''), title),
                author = ?,
                authors = ?,
                year = ?,
                publication_title = ?,
                doi = ?,
                source_url = ?,
                abstract = ?,
                notes = ?,
                attachment_path = ?,
                source = ?,
                zotero_key = ?,
                zotero_item_type = ?,
                tags = ?,
                updated_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (
                metadata.get("title", ""),
                "; ".join(authors),
                json.dumps(authors, ensure_ascii=False),
                str(metadata.get("year", "") or ""),
                metadata.get("publicationTitle", "") or metadata.get("journal", ""),
                metadata.get("DOI", "") or metadata.get("doi", ""),
                metadata.get("url", ""),
                metadata.get("abstract", ""),
                metadata.get("notes", ""),
                metadata.get("attachment_path", "") or metadata.get("pdf_path", ""),
                metadata.get("source", ""),
                metadata.get("key", ""),
                metadata.get("itemType", "") or metadata.get("type", ""),
                json.dumps(tags, ensure_ascii=False),
                document_id,
            ),
        )
        conn.commit()
        conn.close()
        if row:
            MaterialLibraryRepo.touch(row["library_id"])

    @staticmethod
    def search_references(library_id, query="", author="", year="", tag="", journal="", limit=50):
        """Search Zotero-style reference records by bibliographic filters."""
        clauses = ["library_id = ?", "source_type = 'zotero'"]
        params = [int(library_id)]
        if query:
            like = f"%{query}%"
            clauses.append(
                """(
                    title LIKE ? OR abstract LIKE ? OR notes LIKE ? OR publication_title LIKE ?
                    OR doi LIKE ? OR source_url LIKE ? OR author LIKE ?
                )"""
            )
            params.extend([like, like, like, like, like, like, like])
        if author:
            clauses.append("author LIKE ?")
            params.append(f"%{author}%")
        if year:
            clauses.append("year = ?")
            params.append(str(year))
        if tag:
            clauses.append("tags LIKE ?")
            params.append(f"%{tag}%")
        if journal:
            clauses.append("publication_title LIKE ?")
            params.append(f"%{journal}%")
        sql = f"""
            SELECT *
            FROM library_documents
            WHERE {' AND '.join(clauses)}
            ORDER BY year DESC, title COLLATE NOCASE, id DESC
            LIMIT ?
        """
        conn = get_connection()
        rows = conn.execute(sql, [*params, int(limit)]).fetchall()
        conn.close()
        return [dict(r) for r in rows]


class DocumentChunkRepo:
    """CRUD and search helpers for document_chunks."""

    @staticmethod
    def fts_available():
        conn = get_connection()
        try:
            conn.execute("SELECT rowid FROM document_chunks_fts LIMIT 1").fetchone()
            return True
        except Exception:
            return False
        finally:
            conn.close()

    @staticmethod
    def replace_for_document(document_id, library_id, chunks):
        conn = get_connection()
        conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        try:
            conn.execute("DELETE FROM document_chunks_fts WHERE document_id = ?", (document_id,))
        except Exception:
            pass
        ids = []
        for chunk in chunks:
            cur = conn.execute(
                """
                INSERT INTO document_chunks
                (library_id, document_id, chunk_index, section_title, page_start, page_end,
                 char_start, char_end, locator, text, char_count, token_count, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    library_id,
                    document_id,
                    chunk.get("chunk_index", 0),
                    chunk.get("section_title", ""),
                    chunk.get("page_start", 0),
                    chunk.get("page_end", 0),
                    chunk.get("char_start", 0),
                    chunk.get("char_end", 0),
                    chunk.get("locator", ""),
                    chunk.get("text", ""),
                    chunk.get("char_count", len(chunk.get("text", ""))),
                    chunk.get("token_count", chunk.get("char_count", len(chunk.get("text", "")))),
                    json.dumps(chunk.get("metadata", {}), ensure_ascii=False),
                ),
            )
            chunk_id = cur.lastrowid
            ids.append(chunk_id)
            try:
                conn.execute(
                    """
                    INSERT INTO document_chunks_fts(rowid, text, section_title, document_id, library_id)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (chunk_id, chunk.get("text", ""), chunk.get("section_title", ""), document_id, library_id),
                )
            except Exception:
                pass
        conn.commit()
        conn.close()
        return ids

    @staticmethod
    def list_by_document(document_id, limit=200):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index LIMIT ?",
            (document_id, limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def search(library_ids, query, limit=8, folder_id=None):
        library_ids = [int(x) for x in (library_ids or []) if str(x).strip()]
        if not library_ids or not query.strip():
            return []
        folder_filter = DocumentChunkRepo._folder_filter(library_ids, folder_id)
        if folder_filter == ([], True):
            return []
        return (
            DocumentChunkRepo._search_fts(library_ids, query, limit, folder_filter)
            or DocumentChunkRepo._search_like(library_ids, query, limit, folder_filter)
        )

    @staticmethod
    def _folder_filter(library_ids, folder_id):
        if folder_id in (None, "", 0, "0"):
            return None
        if folder_id == "uncategorized":
            return ("uncategorized", False)
        if len(library_ids) != 1:
            return None
        folder_ids = MaterialFolderRepo.descendant_ids(library_ids[0], folder_id)
        return (folder_ids, True)

    @staticmethod
    def _folder_sql(alias, folder_filter):
        if not folder_filter:
            return "", []
        folder_ids, _ = folder_filter
        if folder_ids == "uncategorized":
            return f" AND {alias}.folder_id IS NULL", []
        if not folder_ids:
            return " AND 1 = 0", []
        placeholders = ",".join("?" for _ in folder_ids)
        return f" AND {alias}.folder_id IN ({placeholders})", folder_ids

    @staticmethod
    def _search_fts(library_ids, query, limit, folder_filter=None):
        terms = [t.replace('"', ' ').strip() for t in query.split() if t.strip()]
        if not terms:
            terms = [query.replace('"', ' ').strip()]
        fts_query = " OR ".join(f'"{t}"' for t in terms if t)
        if not fts_query:
            return []
        placeholders = ",".join("?" for _ in library_ids)
        folder_sql, folder_params = DocumentChunkRepo._folder_sql("d", folder_filter)
        sql = f"""
            SELECT
                c.*,
                d.title AS document_title,
                d.original_filename,
                d.folder_id,
                d.tags,
                d.source_type,
                d.source_url,
                d.author,
                d.authors,
                d.year,
                d.publication_title,
                d.doi,
                d.abstract,
                d.notes,
                d.attachment_path,
                d.source,
                d.zotero_key,
                d.zotero_item_type,
                f.name AS folder_name,
                l.name AS library_name,
                bm25(document_chunks_fts) AS rank
            FROM document_chunks_fts
            JOIN document_chunks c ON c.id = document_chunks_fts.rowid
            JOIN library_documents d ON d.id = c.document_id
            LEFT JOIN material_library_folders f ON f.id = d.folder_id
            JOIN material_libraries l ON l.id = c.library_id
            WHERE document_chunks_fts MATCH ?
              AND c.library_id IN ({placeholders})
              {folder_sql}
            ORDER BY rank
            LIMIT ?
        """
        conn = get_connection()
        try:
            rows = conn.execute(sql, [fts_query, *library_ids, *folder_params, limit]).fetchall()
        except Exception:
            conn.close()
            return []
        conn.close()
        results = []
        for idx, row in enumerate(rows):
            item = dict(row)
            rank = abs(float(item.pop("rank", 0) or 0))
            item["score"] = max(0.01, 1.0 / (1.0 + rank + idx * 0.05))
            item["match_type"] = "fts"
            results.append(item)
        return results

    @staticmethod
    def _search_like(library_ids, query, limit, folder_filter=None):
        terms = [t.strip() for t in query.split() if t.strip()] or [query.strip()]
        clauses = []
        params = []
        for term in terms[:6]:
            clauses.append("(c.text LIKE ? OR c.section_title LIKE ? OR d.title LIKE ?)")
            like = f"%{term}%"
            params.extend([like, like, like])
        placeholders = ",".join("?" for _ in library_ids)
        folder_sql, folder_params = DocumentChunkRepo._folder_sql("d", folder_filter)
        sql = f"""
            SELECT
                c.*,
                d.title AS document_title,
                d.original_filename,
                d.folder_id,
                d.tags,
                d.source_type,
                d.source_url,
                d.author,
                d.authors,
                d.year,
                d.publication_title,
                d.doi,
                d.abstract,
                d.notes,
                d.attachment_path,
                d.source,
                d.zotero_key,
                d.zotero_item_type,
                f.name AS folder_name,
                l.name AS library_name
            FROM document_chunks c
            JOIN library_documents d ON d.id = c.document_id
            LEFT JOIN material_library_folders f ON f.id = d.folder_id
            JOIN material_libraries l ON l.id = c.library_id
            WHERE c.library_id IN ({placeholders})
              {folder_sql}
              AND ({' OR '.join(clauses)})
            ORDER BY c.document_id DESC, c.chunk_index
            LIMIT ?
        """
        conn = get_connection()
        rows = conn.execute(sql, [*library_ids, *folder_params, *params, limit]).fetchall()
        conn.close()
        results = []
        for row in rows:
            item = dict(row)
            haystack = (item.get("section_title", "") + "\n" + item.get("text", "")).lower()
            hits = sum(1 for term in terms if term.lower() in haystack)
            item["score"] = hits or 0.5
            item["match_type"] = "like"
            results.append(item)
        return results


class RetrievalSnapshotRepo:
    """CRUD for generation_retrieval_snapshots."""

    @staticmethod
    def create(session_id, library_ids, query, retrieval_policy, evidence):
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO generation_retrieval_snapshots
            (session_id, library_ids, query, retrieval_policy, evidence_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                json.dumps(library_ids or [], ensure_ascii=False),
                query,
                json.dumps(retrieval_policy or {}, ensure_ascii=False),
                json.dumps(evidence or {}, ensure_ascii=False),
            ),
        )
        snapshot_id = cur.lastrowid
        conn.commit()
        conn.close()
        SessionRepo.set_retrieval_snapshot(session_id, snapshot_id)
        return snapshot_id

    @staticmethod
    def get(snapshot_id):
        conn = get_connection()
        row = conn.execute("SELECT * FROM generation_retrieval_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


class ArticleCitationRepo:
    """CRUD for parsed article citations."""

    @staticmethod
    def create(article_id, snapshot_id, source_label, document_id, chunk_id, quoted_text="", citation_text=""):
        conn = get_connection()
        cur = conn.execute(
            """
            INSERT INTO article_citations
            (article_id, snapshot_id, source_label, document_id, chunk_id, quoted_text, citation_text)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (article_id, snapshot_id, source_label, document_id, chunk_id, quoted_text, citation_text),
        )
        citation_id = cur.lastrowid
        conn.commit()
        conn.close()
        return citation_id

    @staticmethod
    def list_by_article(article_id):
        conn = get_connection()
        rows = conn.execute(
            "SELECT * FROM article_citations WHERE article_id = ? ORDER BY id",
            (article_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    @staticmethod
    def delete_by_article(article_id):
        """Remove all citation records for an article (e.g. before re-verification)."""
        conn = get_connection()
        conn.execute("DELETE FROM article_citations WHERE article_id = ?", (article_id,))
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
