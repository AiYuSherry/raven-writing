"""Zotero-style reference-library adapter for the writing desk.

The adapter intentionally works from explicit export files or pasted metadata.
It does not read a private Zotero account, write to a Zotero database, or try to
download paywalled papers.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

from .db.repository import DocumentChunkRepo, LibraryDocumentRepo
from .material_library.extractors import extract, extract_text
from .material_library.chunker import chunk_document
from .material_library import storage


SUPPORTED_FORMATS = {"bibtex", "bib", "csl-json", "csljson", "json", "ris"}


@dataclass
class ZoteroReference:
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    publicationTitle: str = ""
    DOI: str = ""
    url: str = ""
    abstract: str = ""
    tags: list[str] = field(default_factory=list)
    notes: str = ""
    attachment_path: str = ""
    source: str = ""
    key: str = ""
    itemType: str = ""

    def normalized(self) -> dict:
        return {
            "title": self.title.strip(),
            "authors": [a.strip() for a in self.authors if a and a.strip()],
            "year": str(self.year or "").strip(),
            "publicationTitle": self.publicationTitle.strip(),
            "DOI": self.DOI.strip(),
            "url": self.url.strip(),
            "abstract": self.abstract.strip(),
            "tags": [t.strip() for t in self.tags if t and t.strip()],
            "notes": self.notes.strip(),
            "attachment_path": self.attachment_path.strip(),
            "source": self.source.strip(),
            "key": self.key.strip(),
            "itemType": self.itemType.strip(),
        }


def detect_format(filename="", text=""):
    """Best-effort import-format detector."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext == ".bib":
        return "bibtex"
    if ext in {".ris", ".enw"}:
        return "ris"
    if ext == ".json":
        return "csl-json"
    stripped = (text or "").lstrip()
    if stripped.startswith("@"):
        return "bibtex"
    if stripped.startswith("TY  -"):
        return "ris"
    if stripped.startswith("[") or stripped.startswith("{"):
        return "csl-json"
    return ""


def parse_references(text, fmt):
    """Parse exported Zotero-compatible metadata into normalized references."""
    fmt = (fmt or detect_format(text=text) or "").lower()
    if fmt in {"bib", "bibtex"}:
        return parse_bibtex(text)
    if fmt in {"json", "csl-json", "csljson"}:
        return parse_csl_json(text)
    if fmt == "ris":
        return parse_ris(text)
    raise ValueError(f"暂不支持的 Zotero 导入格式: {fmt}")


def parse_csl_json(text):
    """Parse CSL JSON exported from Zotero or Better BibTeX."""
    payload = json.loads(text or "[]")
    if isinstance(payload, dict):
        if isinstance(payload.get("items"), list):
            items = payload["items"]
        elif isinstance(payload.get("data"), list):
            items = payload["data"]
        else:
            items = [payload]
    else:
        items = payload
    refs = []
    for item in items:
        if not isinstance(item, dict):
            continue
        refs.append(_reference_from_csl(item).normalized())
    return refs


def parse_bibtex(text):
    """Parse a practical subset of BibTeX exported by Zotero/Better BibTeX."""
    refs = []
    for entry_type, key, body in _iter_bibtex_entries(text or ""):
        fields = _parse_bibtex_fields(body)
        title = _clean_bib_value(fields.get("title", ""))
        journal = (
            fields.get("journaltitle")
            or fields.get("journal")
            or fields.get("booktitle")
            or fields.get("publisher")
            or ""
        )
        year = _year(fields.get("year") or fields.get("date") or fields.get("urldate") or "")
        tags = _split_tags(fields.get("keywords") or fields.get("tags") or "")
        attachment = fields.get("file") or fields.get("local-url") or fields.get("pdf") or ""
        refs.append(
            ZoteroReference(
                title=title,
                authors=_parse_bibtex_authors(fields.get("author") or fields.get("editor") or ""),
                year=year,
                publicationTitle=_clean_bib_value(journal),
                DOI=_clean_bib_value(fields.get("doi", "")),
                url=_clean_bib_value(fields.get("url", "")),
                abstract=_clean_bib_value(fields.get("abstract", "")),
                tags=tags,
                notes=_clean_bib_value(fields.get("note") or fields.get("annote") or ""),
                attachment_path=_clean_bib_value(attachment),
                source="BibTeX",
                key=key,
                itemType=entry_type,
            ).normalized()
        )
    return refs


def parse_ris(text):
    """Parse RIS records exported by Zotero or another reference manager."""
    records = []
    current = {}
    last_tag = ""
    for raw_line in (text or "").splitlines():
        if not raw_line.strip():
            continue
        match = re.match(r"^([A-Z0-9]{2})  -\s?(.*)$", raw_line)
        if match:
            tag, value = match.group(1), match.group(2).strip()
            if tag == "TY":
                current = {"TY": [value]}
                records.append(current)
            elif tag == "ER":
                current = {}
            else:
                current.setdefault(tag, []).append(value)
            last_tag = tag
        elif current and last_tag:
            current[last_tag][-1] = (current[last_tag][-1] + " " + raw_line.strip()).strip()

    refs = []
    for record in records:
        title = _first(record, "T1", "TI", "CT", "BT")
        authors = []
        for tag in ("AU", "A1", "A2", "A3", "ED"):
            authors.extend(_parse_ris_author(v) for v in record.get(tag, []))
        tags = []
        for kw in record.get("KW", []):
            tags.extend(_split_tags(kw))
        refs.append(
            ZoteroReference(
                title=title,
                authors=[a for a in authors if a],
                year=_year(_first(record, "PY", "Y1", "DA")),
                publicationTitle=_first(record, "JF", "JO", "JA", "T2", "J2", "PB"),
                DOI=_first(record, "DO"),
                url=_first(record, "UR"),
                abstract=_first(record, "AB", "N2"),
                tags=tags,
                notes="\n\n".join(record.get("N1", []) + record.get("NO", [])),
                attachment_path=_first(record, "L1", "L2", "AV"),
                source="RIS",
                key=_first(record, "ID") or _first(record, "M1"),
                itemType=_first(record, "TY"),
            ).normalized()
        )
    return [ref for ref in refs if ref.get("title")]


def import_references(library_id, references, folder_id=None, import_source="zotero-export"):
    """Import references into the existing material-library tables."""
    imported = []
    for ref in references:
        ref = _coerce_reference(ref, import_source=import_source)
        if not ref["title"]:
            continue
        text = reference_to_material_text(ref)
        saved = storage.save_text(library_id, _filename_for_reference(ref), text)
        doc_id = LibraryDocumentRepo.create(
            library_id=library_id,
            title=ref["title"],
            original_filename=saved["filename"],
            file_path=saved["path"],
            source_type="zotero",
            source_url=ref.get("url", ""),
            sha256=saved["sha256"],
            folder_id=folder_id,
            tags=ref.get("tags") or [],
        )
        LibraryDocumentRepo.update_reference_metadata(doc_id, ref)
        extracted = extract_text(ref["title"], text)
        chunks = _chunks_for_reference(ref, extracted)
        DocumentChunkRepo.replace_for_document(doc_id, library_id, chunks)
        LibraryDocumentRepo.update_parse_result(
            doc_id,
            "ready",
            page_count=1,
            word_count=len(text),
            text_preview=text[:1200],
            parse_error="",
            title=ref["title"],
        )
        imported.append({"document_id": doc_id, **ref})
    return imported


def import_file(library_id, path, fmt="", folder_id=None):
    """Read a BibTeX/CSL JSON export file and import it into a library."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        text = f.read()
    fmt = fmt or detect_format(path, text)
    refs = parse_references(text, fmt)
    return import_references(library_id, refs, folder_id=folder_id, import_source=os.path.basename(path))


def import_pdf_file(library_id, path, folder_id=None, metadata=None):
    """Import a local PDF as a Zotero-style reference item."""
    with open(path, "rb") as f:
        data = f.read()
    return import_pdf_bytes(
        library_id,
        os.path.basename(path),
        data,
        folder_id=folder_id,
        metadata=metadata,
    )


def import_pdf_bytes(library_id, filename, data, folder_id=None, metadata=None):
    """Save, parse, chunk, and index one PDF as a Zotero-style reference."""
    if not (filename or "").lower().endswith(".pdf"):
        raise ValueError("Zotero-style PDF 导入只接受 .pdf 文件。")
    if not data:
        raise ValueError("PDF 文件为空。")

    metadata = metadata or {}
    saved = storage.save_bytes(library_id, filename, data)
    try:
        extracted = extract(saved["path"], "pdf")
    except Exception as e:
        raise RuntimeError(f"PDF 解析失败：{e}") from e

    title = (
        (metadata.get("title") or "").strip()
        or _title_from_pdf_text(extracted.text)
        or _title_from_filename(filename)
    )
    abstract = (metadata.get("abstract") or "").strip() or _abstract_from_pdf_text(extracted.text)
    ref = ZoteroReference(
        title=title,
        authors=_coerce_authors(metadata.get("authors") or metadata.get("author") or []),
        year=str(metadata.get("year") or "").strip(),
        publicationTitle=str(metadata.get("publicationTitle") or metadata.get("journal") or "").strip(),
        DOI=str(metadata.get("DOI") or metadata.get("doi") or "").strip(),
        url=str(metadata.get("url") or metadata.get("URL") or "").strip(),
        abstract=abstract,
        tags=_split_tags(metadata.get("tags") or []),
        notes=str(metadata.get("notes") or metadata.get("note") or "").strip(),
        attachment_path=saved["path"],
        source="PDF",
        key=os.path.splitext(os.path.basename(filename or ""))[0],
        itemType="article",
    ).normalized()

    doc_id = LibraryDocumentRepo.create(
        library_id=library_id,
        title=ref["title"],
        original_filename=filename,
        file_path=saved["path"],
        source_type="zotero",
        source_url=ref.get("url", ""),
        mime_type="application/pdf",
        sha256=saved["sha256"],
        folder_id=folder_id,
        tags=ref.get("tags") or [],
    )
    LibraryDocumentRepo.update_reference_metadata(doc_id, ref)
    chunks = _chunks_for_reference(ref, extracted)
    if not chunks and extracted.text.strip():
        chunks = chunk_document(extract_text(ref["title"], extracted.text), max_chars=1200, overlap_chars=0)
    DocumentChunkRepo.replace_for_document(doc_id, library_id, chunks)
    preview = (extracted.text or "").strip()[:1200]
    LibraryDocumentRepo.update_parse_result(
        doc_id,
        "ready",
        page_count=len(extracted.pages or []),
        word_count=len(extracted.text or ""),
        text_preview=preview,
        parse_error="",
        title=ref["title"],
    )
    return {"document_id": doc_id, "file_path": saved["path"], "chunk_count": len(chunks), **ref}


def search_references(library_id, query="", author="", year="", tag="", journal="", limit=50):
    """Search imported Zotero-style items by keyword and bibliographic filters."""
    rows = LibraryDocumentRepo.search_references(
        library_id,
        query=query,
        author=author,
        year=year,
        tag=tag,
        journal=journal,
        limit=limit,
    )
    return [_row_to_reference(row) for row in rows]


def export_references(library_id, fmt="csl-json"):
    """Export imported Zotero-style references as CSL JSON or BibTeX."""
    refs = search_references(library_id, limit=10000)
    fmt = (fmt or "csl-json").lower()
    if fmt in {"json", "csl-json", "csljson"}:
        return export_csl_json(refs)
    if fmt in {"bib", "bibtex"}:
        return export_bibtex(refs)
    raise ValueError(f"暂不支持的导出格式: {fmt}")


def export_csl_json(refs):
    """Export references to a Zotero/CSL compatible JSON string."""
    items = []
    for ref in refs:
        ref = _coerce_reference(ref)
        item = {
            "id": ref.get("key") or f"doc-{ref.get('document_id', '')}",
            "type": _csl_type(ref.get("itemType")),
            "title": ref.get("title", ""),
            "author": [_csl_author(author) for author in ref.get("authors") or []],
            "issued": {"date-parts": [[int(ref["year"])]]} if str(ref.get("year", "")).isdigit() else {},
            "container-title": ref.get("publicationTitle", ""),
            "DOI": ref.get("DOI", ""),
            "URL": ref.get("url", ""),
            "abstract": ref.get("abstract", ""),
            "keyword": ", ".join(ref.get("tags") or []),
            "note": ref.get("notes", ""),
        }
        item = {k: v for k, v in item.items() if v not in ("", [], {})}
        items.append(item)
    return json.dumps(items, ensure_ascii=False, indent=2)


def export_bibtex(refs):
    """Export references to simple BibTeX."""
    entries = []
    for ref in refs:
        ref = _coerce_reference(ref)
        entry_type = _bibtex_type(ref.get("itemType"))
        key = _bibtex_key(ref)
        fields = {
            "title": ref.get("title", ""),
            "author": " and ".join(ref.get("authors") or []),
            "year": ref.get("year", ""),
            "journal": ref.get("publicationTitle", ""),
            "doi": ref.get("DOI", ""),
            "url": ref.get("url", ""),
            "abstract": ref.get("abstract", ""),
            "keywords": ", ".join(ref.get("tags") or []),
            "note": ref.get("notes", ""),
            "file": ref.get("attachment_path", ""),
        }
        lines = [f"@{entry_type}{{{key},"]
        for name, value in fields.items():
            if value:
                lines.append(f"  {name} = {{{_escape_bibtex(value)}}},")
        if lines[-1].endswith(","):
            lines[-1] = lines[-1][:-1]
        lines.append("}")
        entries.append("\n".join(lines))
    return "\n\n".join(entries) + ("\n" if entries else "")


def build_reference_pack(library_ids, query, top_k=6, citation_style="chinese", folder_id=None):
    """Build AI-ready reference cards with citations and key chunks."""
    from .material_library.retrieval import search

    hits = search(library_ids, query or "", top_k=max(top_k * 3, top_k), folder_id=folder_id)
    cards = []
    by_doc = {}
    for hit in hits:
        if hit.get("source_type") != "zotero":
            continue
        doc_id = hit["document_id"]
        if doc_id not in by_doc:
            ref = _reference_from_hit(hit)
            by_doc[doc_id] = {
                "label": f"R{len(by_doc) + 1}",
                "document_id": doc_id,
                "reference": ref,
                "citation": format_citation(ref, style=citation_style),
                "snippets": [],
            }
        if len(by_doc[doc_id]["snippets"]) < 3:
            by_doc[doc_id]["snippets"].append({
                "source_label": hit.get("label"),
                "chunk_id": hit.get("chunk_id"),
                "locator": hit.get("locator"),
                "text": hit.get("excerpt") or hit.get("snippet") or "",
            })
    cards = list(by_doc.values())[:top_k]
    lines = [
        "## 参考文献包",
        f"检索问题：{query or '未填写'}",
        f"引用格式：{'APA 简版' if citation_style == 'apa' else '中文友好'}",
    ]
    if not cards:
        lines.extend(["", "未检索到 Zotero-style 文献卡。"])
    for card in cards:
        ref = card["reference"]
        lines.extend([
            "",
            f"[{card['label']}] {card['citation']}",
            f"document_id={card['document_id']}",
            f"作者年份：{_author_year(ref)}",
            f"题名：{ref.get('title', '')}",
            f"期刊/出版物：{ref.get('publicationTitle') or '未填'}",
            f"DOI/URL：{ref.get('DOI') or ref.get('url') or '未填'}",
        ])
        if ref.get("abstract"):
            lines.append(f"摘要：{ref['abstract'][:520]}")
        if ref.get("notes"):
            lines.append(f"笔记：{ref['notes'][:360]}")
        if ref.get("attachment_path"):
            lines.append(f"PDF/附件：{ref['attachment_path']}")
        if card["snippets"]:
            lines.append("关键片段：")
            for snippet in card["snippets"]:
                lines.append(
                    f"- [{snippet['source_label']}] chunk_id={snippet['chunk_id']} "
                    f"{snippet['locator']}: {snippet['text']}"
                )
    return {"query": query or "", "citation_style": citation_style, "cards": cards, "pack": "\n".join(lines).strip()}


def get_reference(document_id):
    """Return one imported reference by document id."""
    row = LibraryDocumentRepo.get(document_id)
    if not row or row.get("source_type") != "zotero":
        return None
    return _row_to_reference(row)


def reference_to_material_text(ref):
    """Turn one reference into searchable writing-desk material."""
    authors = "；".join(ref.get("authors") or []) or ref.get("author", "")
    tags = "，".join(ref.get("tags") or [])
    citation = format_citation(ref)
    lines = [
        f"题名：{ref.get('title', '')}",
        f"作者：{authors}",
        f"年份：{ref.get('year', '')}",
        f"期刊/出版物：{ref.get('publicationTitle', '')}",
        f"DOI：{ref.get('DOI', '')}",
        f"URL：{ref.get('url', '')}",
        f"标签：{tags}",
        f"来源：{ref.get('source', '')}",
        f"附件路径：{ref.get('attachment_path', '')}",
        "",
        "引用信息：",
        citation,
        "",
        "摘要：",
        ref.get("abstract", "") or "未提供摘要。",
    ]
    notes = ref.get("notes", "")
    if notes:
        lines.extend(["", "笔记：", notes])
    return "\n".join(lines).strip()


def build_writing_snippet(ref_or_document_id, citation_style="chinese"):
    """Return a copyable writing/citation material snippet."""
    if isinstance(ref_or_document_id, int):
        ref = get_reference(ref_or_document_id)
    else:
        ref = _coerce_reference(ref_or_document_id)
    if not ref:
        return ""
    parts = [
        "## 可复制引用素材",
        f"题名：{ref.get('title', '')}",
        f"作者年份：{_author_year(ref)}",
        f"出处：{ref.get('publicationTitle', '')}",
    ]
    if ref.get("DOI"):
        parts.append(f"DOI：{ref['DOI']}")
    if ref.get("url"):
        parts.append(f"URL：{ref['url']}")
    if ref.get("abstract"):
        parts.extend(["", "摘要/可用论据：", ref["abstract"]])
    if ref.get("notes"):
        parts.extend(["", "笔记：", ref["notes"]])
    parts.extend(["", "引用信息：", format_citation(ref, style=citation_style)])
    if ref.get("attachment_path"):
        parts.append(f"附件/PDF：{ref['attachment_path']}")
    return "\n".join(parts).strip()


def format_citation(ref, style="chinese"):
    """Create a citation line without requiring external CSL dependencies."""
    ref = _coerce_reference(ref)
    authors = ref.get("authors") or []
    if style == "apa":
        return _format_apa_citation(ref, authors)
    author_text = "、".join(authors[:3])
    if len(authors) > 3:
        author_text += "等"
    if not author_text:
        author_text = "佚名"
    year = ref.get("year") or "n.d."
    title = ref.get("title") or "未命名文献"
    journal = ref.get("publicationTitle") or ""
    doi = ref.get("DOI") or ""
    url = ref.get("url") or ""
    tail = "；".join(x for x in [journal, f"DOI: {doi}" if doi else "", url] if x)
    return f"{author_text}（{year}）：《{title}》" + (f"，{tail}。" if tail else "。")


def _format_apa_citation(ref, authors):
    year = ref.get("year") or "n.d."
    title = ref.get("title") or "Untitled"
    journal = ref.get("publicationTitle") or ""
    doi = ref.get("DOI") or ""
    url = ref.get("url") or ""
    if authors:
        author_text = ", ".join(_apa_name(a) for a in authors[:20])
    else:
        author_text = "Anonymous"
    parts = [f"{author_text} ({year}). {title}."]
    if journal:
        parts.append(f" {journal}.")
    if doi:
        parts.append(f" https://doi.org/{doi.removeprefix('https://doi.org/')}")
    elif url:
        parts.append(f" {url}")
    return "".join(parts)


def _chunks_for_reference(ref, extracted):
    """Build AI-oriented chunks: metadata card first, then body/PDF chunks."""
    card_text = reference_to_material_text(ref)
    chunks = [{
        "chunk_index": 0,
        "section_title": "文献引用卡",
        "page_start": 0,
        "page_end": 0,
        "char_start": 0,
        "char_end": len(card_text),
        "locator": "reference card",
        "text": card_text,
        "char_count": len(card_text),
        "token_count": len(card_text),
        "metadata": {"kind": "reference_card"},
    }]
    body_chunks = chunk_document(extracted, max_chars=900, overlap_chars=100)
    for index, chunk in enumerate(body_chunks, start=1):
        chunk = dict(chunk)
        chunk["chunk_index"] = index
        chunk["metadata"] = {**(chunk.get("metadata") or {}), "kind": "source_text"}
        chunks.append(chunk)
    return chunks


def _reference_from_hit(hit):
    return _coerce_reference({
        "document_id": hit.get("document_id"),
        "title": hit.get("document_title") or "",
        "authors": hit.get("authors") or hit.get("author") or [],
        "year": hit.get("year") or "",
        "publicationTitle": hit.get("publication_title") or "",
        "DOI": hit.get("doi") or "",
        "url": hit.get("source_url") or "",
        "abstract": hit.get("abstract") or "",
        "notes": hit.get("notes") or "",
        "tags": hit.get("tags") or [],
        "attachment_path": hit.get("attachment_path") or "",
        "source": hit.get("source") or "",
        "key": hit.get("zotero_key") or "",
        "itemType": hit.get("zotero_item_type") or "",
    })


def _first(record, *tags):
    for tag in tags:
        values = record.get(tag) or []
        for value in values:
            value = str(value or "").strip()
            if value:
                return value
    return ""


def _parse_ris_author(value):
    value = str(value or "").strip()
    if "," in value:
        family, given = [part.strip() for part in value.split(",", 1)]
        return " ".join(x for x in [given, family] if x)
    return value


def _csl_author(author):
    author = str(author or "").strip()
    if not author:
        return {}
    parts = author.split()
    if len(parts) == 1:
        return {"literal": author}
    return {"given": " ".join(parts[:-1]), "family": parts[-1]}


def _csl_type(item_type):
    lowered = str(item_type or "").lower()
    if "book" in lowered:
        return "book"
    if "chapter" in lowered:
        return "chapter"
    if "conference" in lowered or "conf" in lowered:
        return "paper-conference"
    return "article-journal"


def _bibtex_type(item_type):
    lowered = str(item_type or "").lower()
    if "book" in lowered:
        return "book"
    if "chapter" in lowered:
        return "inbook"
    if "conference" in lowered or "conf" in lowered:
        return "inproceedings"
    return "article"


def _bibtex_key(ref):
    key = ref.get("key") or ""
    if not key:
        first_author = (ref.get("authors") or ["anon"])[0].split()[-1].lower()
        key = f"{first_author}{ref.get('year') or 'nd'}"
    return re.sub(r"[^A-Za-z0-9:_-]+", "", key) or "reference"


def _escape_bibtex(value):
    return str(value or "").replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _apa_name(author):
    author = str(author or "").strip()
    if not author:
        return ""
    parts = author.split()
    if len(parts) == 1:
        return author
    family = parts[-1]
    initials = " ".join(f"{p[0]}." for p in parts[:-1] if p)
    return f"{family}, {initials}".strip()


def _reference_from_csl(item):
    authors = []
    for creator in item.get("author") or item.get("editor") or []:
        if not isinstance(creator, dict):
            continue
        literal = creator.get("literal", "")
        if literal:
            authors.append(literal)
            continue
        given = creator.get("given", "")
        family = creator.get("family", "")
        name = " ".join(x for x in [given, family] if x).strip()
        if name:
            authors.append(name)
    year = _year(item.get("issued") or item.get("date") or "")
    tags = item.get("keyword") or item.get("keywords") or item.get("tags") or []
    if isinstance(tags, str):
        tags = _split_tags(tags)
    return ZoteroReference(
        title=str(item.get("title") or ""),
        authors=authors,
        year=year,
        publicationTitle=str(
            item.get("container-title")
            or item.get("publicationTitle")
            or item.get("journal")
            or item.get("publisher")
            or ""
        ),
        DOI=str(item.get("DOI") or item.get("doi") or ""),
        url=str(item.get("URL") or item.get("url") or ""),
        abstract=str(item.get("abstract") or item.get("abstractNote") or ""),
        tags=tags,
        notes=_notes_from_csl(item),
        attachment_path=str(item.get("attachment_path") or item.get("pdf_path") or item.get("file") or ""),
        source=str(item.get("source") or "CSL JSON"),
        key=str(item.get("id") or item.get("citation-key") or item.get("key") or ""),
        itemType=str(item.get("type") or item.get("itemType") or ""),
    )


def _iter_bibtex_entries(text):
    pos = 0
    while True:
        match = re.search(r"@([A-Za-z]+)\s*\{\s*([^,\s]+)\s*,", text[pos:])
        if not match:
            break
        start = pos + match.start()
        body_start = pos + match.end()
        depth = 1
        i = body_start
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        body = text[body_start:i - 1]
        yield match.group(1).strip(), match.group(2).strip(), body
        pos = i


def _parse_bibtex_fields(body):
    fields = {}
    i = 0
    while i < len(body):
        while i < len(body) and body[i] in ", \n\r\t":
            i += 1
        name_match = re.match(r"([A-Za-z][A-Za-z0-9_-]*)\s*=", body[i:])
        if not name_match:
            break
        name = name_match.group(1).lower()
        i += name_match.end()
        while i < len(body) and body[i].isspace():
            i += 1
        value, i = _read_bibtex_value(body, i)
        fields[name] = _clean_bib_value(value)
    return fields


def _read_bibtex_value(body, i):
    if i >= len(body):
        return "", i
    if body[i] == "{":
        depth = 1
        i += 1
        start = i
        while i < len(body) and depth:
            if body[i] == "{":
                depth += 1
            elif body[i] == "}":
                depth -= 1
                if depth == 0:
                    value = body[start:i]
                    return value, i + 1
            i += 1
        return body[start:i], i
    if body[i] == '"':
        i += 1
        start = i
        escaped = False
        while i < len(body):
            if body[i] == '"' and not escaped:
                return body[start:i], i + 1
            escaped = body[i] == "\\" and not escaped
            if body[i] != "\\":
                escaped = False
            i += 1
        return body[start:i], i
    start = i
    while i < len(body) and body[i] != ",":
        i += 1
    return body[start:i].strip(), i


def _clean_bib_value(value):
    value = str(value or "").strip()
    value = value.replace("\\&", "&").replace("\\_", "_")
    value = re.sub(r"[{}]", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_bibtex_authors(value):
    value = _clean_bib_value(value)
    authors = []
    for raw in re.split(r"\s+\band\b\s+", value):
        raw = raw.strip()
        if not raw:
            continue
        if "," in raw:
            family, given = [part.strip() for part in raw.split(",", 1)]
            raw = " ".join(x for x in [given, family] if x)
        authors.append(raw)
    return authors


def _split_tags(value):
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part.strip() for part in re.split(r"[,;]", str(value or "")) if part.strip()]


def _year(value):
    if isinstance(value, dict):
        parts = value.get("date-parts") or []
        if parts and parts[0]:
            return str(parts[0][0])
    if isinstance(value, list) and value:
        return _year(value[0])
    match = re.search(r"(18|19|20)\d{2}", str(value or ""))
    return match.group(0) if match else ""


def _notes_from_csl(item):
    notes = item.get("note") or item.get("notes") or ""
    if isinstance(notes, list):
        normalized = []
        for note in notes:
            if isinstance(note, dict):
                normalized.append(str(note.get("note") or note.get("text") or ""))
            else:
                normalized.append(str(note))
        return "\n\n".join(n for n in normalized if n.strip())
    return str(notes or "")


def _coerce_reference(ref, import_source=""):
    if isinstance(ref, ZoteroReference):
        ref = ref.normalized()
    ref = dict(ref or {})
    authors = ref.get("authors") or ref.get("author") or []
    if isinstance(authors, str):
        try:
            parsed_authors = json.loads(authors)
            authors = parsed_authors if isinstance(parsed_authors, list) else authors
        except Exception:
            pass
    if isinstance(authors, str):
        authors = [a.strip() for a in re.split(r";|、|,", authors) if a.strip()]
    tags = ref.get("tags") or []
    if isinstance(tags, str):
        try:
            parsed_tags = json.loads(tags)
            tags = parsed_tags if isinstance(parsed_tags, list) else tags
        except Exception:
            pass
    if isinstance(tags, str):
        tags = _split_tags(tags)
    ref["authors"] = authors
    ref["tags"] = tags
    ref["title"] = str(ref.get("title") or "").strip()
    ref["year"] = str(ref.get("year") or "").strip()
    ref["publicationTitle"] = str(ref.get("publicationTitle") or ref.get("journal") or "").strip()
    ref["DOI"] = str(ref.get("DOI") or ref.get("doi") or "").strip()
    ref["url"] = str(ref.get("url") or ref.get("URL") or "").strip()
    ref["abstract"] = str(ref.get("abstract") or ref.get("abstractNote") or "").strip()
    ref["notes"] = str(ref.get("notes") or ref.get("note") or "").strip()
    ref["attachment_path"] = str(ref.get("attachment_path") or ref.get("pdf_path") or "").strip()
    ref["source"] = str(ref.get("source") or import_source or "").strip()
    ref["key"] = str(ref.get("key") or "").strip()
    ref["itemType"] = str(ref.get("itemType") or ref.get("type") or "").strip()
    return ref


def _coerce_authors(authors):
    if isinstance(authors, str):
        return [a.strip() for a in re.split(r";|、|,", authors) if a.strip()]
    return [str(a).strip() for a in authors if str(a).strip()]


def _row_to_reference(row):
    row = dict(row or {})
    try:
        authors = json.loads(row.get("authors") or "[]")
    except Exception:
        authors = []
    if not authors and row.get("author"):
        authors = [a.strip() for a in row["author"].split(";") if a.strip()]
    try:
        tags = json.loads(row.get("tags") or "[]")
    except Exception:
        tags = []
    return {
        "document_id": row.get("id"),
        "title": row.get("title", ""),
        "authors": authors,
        "year": row.get("year", ""),
        "publicationTitle": row.get("publication_title", ""),
        "DOI": row.get("doi", ""),
        "url": row.get("source_url", ""),
        "abstract": row.get("abstract", ""),
        "tags": tags,
        "notes": row.get("notes", ""),
        "attachment_path": row.get("attachment_path", ""),
        "source": row.get("source", ""),
        "key": row.get("zotero_key", ""),
        "itemType": row.get("zotero_item_type", ""),
        "parse_status": row.get("parse_status", ""),
    }


def _filename_for_reference(ref):
    stem = ref.get("key") or ref.get("title") or "zotero-reference"
    return storage.safe_filename(stem, fallback="zotero-reference") + ".txt"


def _author_year(ref):
    authors = ref.get("authors") or []
    if not authors:
        return f"佚名（{ref.get('year') or 'n.d.'}）"
    first = authors[0]
    suffix = "等" if len(authors) > 1 else ""
    return f"{first}{suffix}（{ref.get('year') or 'n.d.'}）"


def _title_from_pdf_text(text):
    for raw in (text or "").splitlines()[:12]:
        line = re.sub(r"\s+", " ", raw).strip()
        if not line:
            continue
        if len(line) < 4 or len(line) > 180:
            continue
        if re.fullmatch(r"\d+|page \d+", line, flags=re.IGNORECASE):
            continue
        return line
    return ""


def _title_from_filename(filename):
    stem = os.path.splitext(os.path.basename(filename or "PDF 文献"))[0]
    stem = re.sub(r"[_-]+", " ", stem).strip()
    return stem or "PDF 文献"


def _abstract_from_pdf_text(text, max_chars=900):
    raw = text or ""
    cleaned = re.sub(r"\s+", " ", raw).strip()
    if not cleaned:
        return ""
    title = _title_from_pdf_text(raw)
    if title:
        cleaned = re.sub(r"^\s*" + re.escape(title) + r"\s*", "", cleaned).strip()
    return cleaned[:max_chars]
