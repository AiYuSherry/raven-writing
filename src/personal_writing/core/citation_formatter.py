"""Citation footnote formatter — replace [Sx] tags with academic footnotes.

Transforms article content from raw ``[Sx]`` markers into numbered inline
references (``[1]``, ``[2]``, …) with a ``## 参考文献`` end-notes section
built from the evidence-pack metadata (author, title, journal, year, page).

Usage::

    from .citation_formatter import format_article_footnotes

    body, notes = format_article_footnotes(content, evidence_results)
"""

import json
import re
from typing import Optional

from .citation_verifier import SX_PATTERN, extract_citation_evidence_map

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def format_article_footnotes(
    content: str,
    evidence_results: Optional[list] = None,
) -> tuple[str, str]:
    """Replace ``[Sx]`` in *content* with sequential ``[1]``, ``[2]``, …

    Parameters
    ----------
    content
        Article body text containing ``[Sx]`` markers.
    evidence_results
        List of evidence dicts from the retrieval snapshot (see
        ``retrieval.py``).  Each dict should have at least *label* and
        *document_title*; ideally also *authors*, *year*,
        *publication_title*, and page info.

    Returns
    -------
    (formatted_body, footnotes_section)
        *formatted_body* — the article with ``[Sx]`` replaced by sequential
        ``[N]`` markers.
        *footnotes_section* — a ``## 参考文献`` Markdown section with
        properly formatted academic footnotes, or ``""`` when there are no
        citations or no evidence.
    """
    evidence_results = evidence_results or []
    evidence_map = extract_citation_evidence_map(evidence_results)

    # Collect all [Sx] occurrences preserving first-seen order
    matches = list(SX_PATTERN.finditer(content))
    if not matches:
        return content, ""

    seen_labels: list[str] = []
    label_to_num: dict[str, int] = {}
    for m in matches:
        lbl = m.group(1)
        if lbl not in label_to_num:
            label_to_num[lbl] = len(label_to_num) + 1
            seen_labels.append(lbl)

    # Replace [Sx] → [N]
    def _replace(m: re.Match) -> str:
        num = label_to_num.get(m.group(1), 0)
        return f"[{num}]"

    formatted_body = SX_PATTERN.sub(_replace, content)

    # Build footnotes
    footnotes = []
    for lbl in seen_labels:
        num = label_to_num[lbl]
        ev = evidence_map.get(lbl)
        footnotes.append(_format_single(num, lbl, ev))

    footnotes_section = "## 参考文献\n\n" + "\n\n".join(footnotes) + "\n"

    return formatted_body, footnotes_section


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_single(num: int, label: str, evidence: Optional[dict]) -> str:
    """Format one citation footnote entry."""
    if not evidence:
        return (
            f"[需补证：{label}] "
            f"该引用在素材库中未找到对应文献信息，请人工补充。"
        )

    authors = _format_authors(evidence)
    title = (
        evidence.get("document_title")
        or evidence.get("original_filename")
        or ""
    )
    publication = evidence.get("publication_title") or ""
    year = evidence.get("year") or ""
    page = _format_page(evidence)

    # --- Full academic footnote (journal article) ---
    #   格式：作者，《题名》，载《期刊名》XXXX年，第X页。
    if authors and title and publication and year:
        base = f"{authors}，《{title}》，载《{publication}》{year}年"
        if page:
            # Strip leading "第" / trailing "页" from *page* so we don't nest them
            raw_page = page.strip()
            if raw_page.startswith("第"):
                raw_page = raw_page[1:]
            if raw_page.endswith("页"):
                raw_page = raw_page[:-1]
            base += f"，第{raw_page}页"
        return f"[{num}] 参见 {base}。"

    # --- Book / monograph (author + title + year, no journal) ---
    if authors and title and year:
        base = f"{authors}，《{title}》{year}年"
        if page:
            base += f"，第{page}"
        return f"[{num}] 参见 {base}。"

    # --- Title only (no author / journal metadata) ---
    if title:
        base = f"《{title}》"
        if year:
            base += f"，{year}年"
        if page:
            base += f"，第{page}"
        return f"[{num}] 参见 {base}。"

    # --- Fallback: missing core metadata ---
    doc = evidence.get("document_title") or evidence.get("original_filename") or ""
    if doc:
        return (
            f"[需补证：{label}] 引用来源“{doc}”缺少完整文献信息"
            f"（作者、期刊、年份），请人工补证。"
        )
    return (
        f"[需补证：{label}] "
        f"该引用在素材库中未找到对应文献信息，请人工补充。"
    )


def _format_authors(evidence: dict) -> str:
    """Extract and format author names."""
    raw = evidence.get("authors") or evidence.get("author") or ""
    authors: list[str] = []

    if isinstance(raw, list):
        authors = [str(a).strip() for a in raw if str(a).strip()]
    elif isinstance(raw, str):
        # Try JSON array first, then fall back to semicolon splitting
        stripped = raw.strip()
        if stripped.startswith("["):
            try:
                authors = json.loads(stripped)
                authors = [str(a).strip() for a in authors if str(a).strip()]
            except (json.JSONDecodeError, TypeError):
                pass
        if not authors:
            authors = [
                a.strip()
                for a in re.split(r"[；;]", stripped)
                if a.strip()
            ]

    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    if len(authors) == 2:
        return "、".join(authors)
    return authors[0] + "等"


def _format_page(evidence: dict) -> str:
    """Extract page string from evidence metadata."""
    locator = (evidence.get("locator") or "").strip()
    ps = evidence.get("page_start") or 0
    pe = evidence.get("page_end") or 0

    # Prefer explicit locator (e.g. "p.45" or "第45页")
    if locator:
        m = re.search(r"(\d+)", locator)
        if m:
            return m.group(1)

    # Fall back to page_start / page_end, showing range only when valid
    if ps:
        if pe and pe != ps:
            return f"{ps}—{pe}"
        return str(ps)

    return ""
