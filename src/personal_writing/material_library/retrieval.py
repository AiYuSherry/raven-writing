"""Keyword retrieval for material libraries."""

from ..db.repository import DocumentChunkRepo


def search(library_ids, query, top_k=8, folder_id=None):
    """Search chunks and return source-aware evidence records."""
    rows = DocumentChunkRepo.search(library_ids, query or "", limit=top_k, folder_id=folder_id)
    results = []
    for idx, row in enumerate(rows, start=1):
        label = f"S{idx}"
        document_title = row.get("document_title") or row.get("original_filename") or f"文档 {row.get('document_id')}"
        locator = row.get("locator") or _locator(row)
        excerpt = _snippet(row.get("text", ""), query)
        results.append({
            "label": label,
            "chunk_id": row["id"],
            "document_id": row["document_id"],
            "library_id": row["library_id"],
            "library_name": row.get("library_name", ""),
            "folder_id": row.get("folder_id"),
            "folder_name": row.get("folder_name", ""),
            "tags": row.get("tags", "[]"),
            "document_title": document_title,
            "original_filename": row.get("original_filename", ""),
            "source_type": row.get("source_type", ""),
            "source_url": row.get("source_url", ""),
            "author": row.get("author", ""),
            "authors": row.get("authors", "[]"),
            "year": row.get("year", ""),
            "publication_title": row.get("publication_title", ""),
            "doi": row.get("doi", ""),
            "abstract": row.get("abstract", ""),
            "notes": row.get("notes", ""),
            "attachment_path": row.get("attachment_path", ""),
            "source": row.get("source", ""),
            "zotero_key": row.get("zotero_key", ""),
            "zotero_item_type": row.get("zotero_item_type", ""),
            "page_start": row.get("page_start", 0),
            "page_end": row.get("page_end", 0),
            "locator": locator,
            "section_title": row.get("section_title", ""),
            "text": row.get("text", ""),
            "snippet": excerpt,
            "excerpt": excerpt,
            "score": row.get("score", 0),
            "match_type": row.get("match_type", ""),
            "citation_label": _citation_label(label, document_title, locator, row),
        })
    return results


def _locator(row):
    page = row.get("page_start") or 0
    if page:
        return f"p.{page}"
    return f"chunk {row.get('chunk_index', 0) + 1}"


def _snippet(text, query, max_chars=360):
    text = (text or "").strip()
    if len(text) <= max_chars:
        return text
    terms = [t for t in (query or "").split() if t]
    hit = -1
    lowered = text.lower()
    for term in terms:
        hit = lowered.find(term.lower())
        if hit >= 0:
            break
    if hit < 0:
        return text[:max_chars].rstrip() + "..."
    start = max(0, hit - max_chars // 3)
    end = min(len(text), start + max_chars)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def _citation_label(label, document_title, locator, row):
    bits = [f"[{label}]", f"《{document_title}》"]
    author = row.get("author") or ""
    year = row.get("year") or ""
    if author:
        bits.append(author)
    if year:
        bits.append(str(year))
    if locator:
        bits.append(locator)
    return " ".join(bits)
