"""Deterministic source-guide and library-index helpers."""

import re
from collections import Counter

from ..db.schema import get_connection


_STOPWORDS = {
    "以及", "因此", "由于", "通过", "进行", "对于", "关于", "可以", "需要", "已经",
    "一个", "一种", "这些", "那些", "本文", "研究", "问题", "材料", "文档", "内容",
    "the", "and", "for", "with", "that", "this", "from", "into", "are", "was",
}


def build_source_guide(document, chunks):
    """Build an extractive, model-free source guide for one document."""
    chunks = chunks or []
    text = _join_text(document, chunks)
    keywords = _keywords(text, document.get("title") or document.get("original_filename") or "")
    title = document.get("title") or document.get("original_filename") or f"文档 {document.get('id')}"
    summary = _summary(text, title)
    return {
        "document_id": document.get("id"),
        "title": title,
        "summary": summary,
        "keywords": keywords,
        "suggested_questions": _suggested_questions(title, keywords),
        "word_count": int(document.get("word_count") or len(text)),
        "page_count": int(document.get("page_count") or 0),
        "chunk_count": len(chunks),
        "folder_id": document.get("folder_id"),
        "folder_name": document.get("folder_name") or "未分类",
        "parse_status": document.get("parse_status") or "queued",
        "source_type": document.get("source_type") or "",
        "authors": document.get("authors") or "[]",
        "year": document.get("year") or "",
        "publication_title": document.get("publication_title") or "",
        "doi": document.get("doi") or "",
        "url": document.get("source_url") or "",
        "attachment_path": document.get("attachment_path") or "",
        "updated_at": document.get("updated_at") or "",
    }


def build_library_index_summary(library_id):
    """Return a source-panel style summary for one material library."""
    conn = get_connection()
    totals = conn.execute(
        """
        SELECT
            COUNT(DISTINCT d.id) AS document_count,
            COUNT(c.id) AS chunk_count,
            COUNT(DISTINCT CASE WHEN d.parse_status = 'ready' THEN d.id END) AS ready_document_count,
            COUNT(DISTINCT CASE WHEN d.parse_status = 'failed' THEN d.id END) AS failed_document_count,
            MAX(COALESCE(c.created_at, d.updated_at, d.created_at)) AS last_indexed_at
        FROM library_documents d
        LEFT JOIN document_chunks c ON c.document_id = d.id
        WHERE d.library_id = ?
        """,
        (library_id,),
    ).fetchone()
    folder_count_row = conn.execute(
        "SELECT COUNT(*) AS folder_count FROM material_library_folders WHERE library_id = ?",
        (library_id,),
    ).fetchone()
    folders = conn.execute(
        """
        SELECT
            f.id AS folder_id,
            f.name AS folder_name,
            COUNT(DISTINCT d.id) AS document_count,
            COUNT(c.id) AS chunk_count,
            COUNT(DISTINCT CASE WHEN d.parse_status = 'ready' THEN d.id END) AS ready_document_count
        FROM material_library_folders f
        LEFT JOIN library_documents d ON d.folder_id = f.id
        LEFT JOIN document_chunks c ON c.document_id = d.id
        WHERE f.library_id = ?
        GROUP BY f.id
        ORDER BY f.parent_id IS NOT NULL, f.sort_order, f.name, f.id
        """,
        (library_id,),
    ).fetchall()
    uncategorized = conn.execute(
        """
        SELECT
            COUNT(DISTINCT d.id) AS document_count,
            COUNT(c.id) AS chunk_count,
            COUNT(DISTINCT CASE WHEN d.parse_status = 'ready' THEN d.id END) AS ready_document_count
        FROM library_documents d
        LEFT JOIN document_chunks c ON c.document_id = d.id
        WHERE d.library_id = ? AND d.folder_id IS NULL
        """,
        (library_id,),
    ).fetchone()
    conn.close()

    totals = dict(totals or {})
    searchable_documents = _searchable_document_count(library_id)
    breakdown = [dict(row) for row in folders]
    if uncategorized and (uncategorized["document_count"] or uncategorized["chunk_count"]):
        breakdown.append({
            "folder_id": None,
            "folder_name": "未分类",
            "document_count": int(uncategorized["document_count"] or 0),
            "chunk_count": int(uncategorized["chunk_count"] or 0),
            "ready_document_count": int(uncategorized["ready_document_count"] or 0),
        })
    return {
        "library_id": library_id,
        "document_count": int(totals.get("document_count") or 0),
        "chunk_count": int(totals.get("chunk_count") or 0),
        "folder_count": int(folder_count_row["folder_count"] or 0) if folder_count_row else 0,
        "ready_document_count": int(totals.get("ready_document_count") or 0),
        "failed_document_count": int(totals.get("failed_document_count") or 0),
        "searchable_document_count": searchable_documents,
        "last_indexed_at": totals.get("last_indexed_at") or "",
        "folder_breakdown": breakdown,
    }


def _searchable_document_count(library_id):
    conn = get_connection()
    row = conn.execute(
        """
        SELECT COUNT(*) AS count FROM (
            SELECT d.id
            FROM library_documents d
            JOIN document_chunks c ON c.document_id = d.id
            WHERE d.library_id = ? AND d.parse_status = 'ready'
            GROUP BY d.id
        )
        """,
        (library_id,),
    ).fetchone()
    conn.close()
    return int(row["count"] or 0) if row else 0


def _join_text(document, chunks):
    parts = []
    preview = (document.get("text_preview") or "").strip()
    if preview:
        parts.append(preview)
    parts.extend((chunk.get("text") or "").strip() for chunk in chunks[:8])
    return "\n\n".join(part for part in parts if part).strip()


def _summary(text, title, max_sentences=3):
    sentences = _sentences(text)
    if not sentences:
        return f"《{title}》已入库，但当前没有可展示的抽取文本。"
    return "".join(sentences[:max_sentences])[:520]


def _sentences(text):
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if not text:
        return []
    pieces = re.split(r"(?<=[。！？!?；;])\s+|(?<=[。！？!?；;])", text)
    return [p.strip() for p in pieces if len(p.strip()) >= 8]


def _keywords(text, title, limit=10):
    counter = Counter()
    source = f"{title}\n{text}"
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", source):
        token = token.strip().lower()
        if token in _STOPWORDS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token) and len(token) > 6:
            for size in (2, 3, 4):
                for i in range(0, len(token) - size + 1):
                    gram = token[i:i + size]
                    if gram not in _STOPWORDS:
                        counter[gram] += 1
        else:
            counter[token] += 1
    return [word for word, _ in counter.most_common(limit)]


def _suggested_questions(title, keywords):
    primary = keywords[:3]
    target = "、".join(primary) if primary else title
    questions = [
        f"这份资料如何界定“{primary[0] if primary else title}”？",
        f"哪些段落可以作为“{target}”的论据？",
        f"这份资料与论文主题的关键关联是什么？",
    ]
    if len(primary) >= 2:
        questions.append(f"{primary[0]}与{primary[1]}之间是什么关系？")
    return questions[:4]
