"""Paragraph-aware chunking for extracted material-library text."""

import re


def chunk_document(extracted, max_chars=900, overlap_chars=100):
    """Return chunk dicts preserving page/section/locator metadata."""
    chunks = []
    index = 0
    pages = extracted.pages or [{"page": 0, "text": extracted.text, "section_title": ""}]
    global_offset = 0
    for page in pages:
        page_no = int(page.get("page") or 0)
        text = page.get("text") or ""
        section = page.get("section_title") or ""
        for chunk_text, start, end in _chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars):
            if not chunk_text.strip():
                continue
            locator = f"p.{page_no}" if page_no else f"chunk {index + 1}"
            chunks.append({
                "chunk_index": index,
                "section_title": section,
                "page_start": page_no,
                "page_end": page_no,
                "char_start": global_offset + start,
                "char_end": global_offset + end,
                "locator": locator,
                "text": chunk_text.strip(),
                "char_count": len(chunk_text.strip()),
                "token_count": len(chunk_text.strip()),
                "metadata": {},
            })
            index += 1
        global_offset += len(text) + 2
    return chunks


def _chunk_text(text, max_chars=900, overlap_chars=100):
    paragraphs = _paragraphs(text)
    chunks = []
    current = []
    current_len = 0
    current_start = 0
    cursor = 0

    for para in paragraphs:
        para_start = text.find(para, cursor)
        if para_start < 0:
            para_start = cursor
        para_end = para_start + len(para)
        cursor = para_end

        if len(para) > max_chars:
            if current:
                joined = "\n\n".join(current)
                chunks.append((joined, current_start, para_start))
                current = []
                current_len = 0
            for piece, start, end in _split_long_para(para, para_start, max_chars, overlap_chars):
                chunks.append((piece, start, end))
            continue

        projected = current_len + len(para) + (2 if current else 0)
        if current and projected > max_chars:
            joined = "\n\n".join(current)
            chunks.append((joined, current_start, para_start))
            tail = _overlap_tail(joined, overlap_chars)
            current = [tail, para] if tail else [para]
            current_len = sum(len(x) for x in current) + 2 * (len(current) - 1)
            current_start = max(current_start, para_start - len(tail)) if tail else para_start
        else:
            if not current:
                current_start = para_start
            current.append(para)
            current_len = projected

    if current:
        chunks.append(("\n\n".join(current), current_start, len(text)))
    return chunks


def _paragraphs(text):
    text = (text or "").replace("\r\n", "\n")
    parts = re.split(r"\n\s*\n|(?<=。)\s*(?=[一二三四五六七八九十\d]+[、.])", text)
    parts = [p.strip() for p in parts if p and p.strip()]
    if parts:
        return parts
    return [text.strip()] if text.strip() else []


def _split_long_para(para, base_start, max_chars, overlap_chars):
    pieces = []
    start = 0
    while start < len(para):
        end = min(len(para), start + max_chars)
        piece = para[start:end]
        pieces.append((piece, base_start + start, base_start + end))
        if end >= len(para):
            break
        start = max(end - overlap_chars, start + 1)
    return pieces


def _overlap_tail(text, overlap_chars):
    if not overlap_chars or len(text) <= overlap_chars:
        return ""
    tail = text[-overlap_chars:].strip()
    return tail if len(tail) >= 20 else ""
