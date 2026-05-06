"""Citation verification engine — extract, verify, and flag AI-generated citations.

Integrates with the evidence pack / retrieval snapshot system to check
whether each [Sx] citation in a generated article references real content
from the material library.
"""

import json
import re
from dataclasses import dataclass, asdict, field
from typing import Optional

from ..db.repository import ArticleRepo, ArticleCitationRepo, RetrievalSnapshotRepo

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class ExtractedCitation:
    """One citation reference extracted from article text."""
    label: str                       # e.g. "S1"
    cited_text: str = ""             # the claim attributed to the source
    context_before: str = ""
    context_after: str = ""
    page_mentioned: str = ""         # page number mentioned in article text


@dataclass
class CitationVerification:
    """Result of verifying one citation against evidence."""
    label: str
    status: str                      # "verified" | "unverifiable" | "hallucinated"
    cited_text: str = ""
    evidence_text: str = ""
    document_title: str = ""
    confidence: float = 0.0
    reason: str = ""


@dataclass
class VerificationResult:
    """Aggregated verification result for one article."""
    citations: list = field(default_factory=list)
    verified_count: int = 0
    unverifiable_count: int = 0
    hallucinated_count: int = 0
    grounding_status: str = "not_checked"

    def to_dict(self) -> dict:
        return {
            "citations": [asdict(c) for c in self.citations],
            "verified_count": self.verified_count,
            "unverifiable_count": self.unverifiable_count,
            "hallucinated_count": self.hallucinated_count,
            "grounding_status": self.grounding_status,
        }


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

SX_PATTERN = re.compile(r"\[(S\d+)\]")
PAGE_PATTERN = re.compile(r"[第共](?P<page>\d+)[页面]")
CHINESE_CITATION_PATTERN = re.compile(
    r"(?:参见?|见)?"
    r"(?P<author>[^，,。！？　]{1,8})"
    r"[，,]\s*[《（(]"
    r"(?P<title>[^》）)]{2,60})"
    r"[》）)]"
    r"(?:[，,]\s*[第共](?P<page>\d+)[页面])?"
)

# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------


def extract_citations(text: str, evidence_results: list = None):
    """Extract [Sx] citations and Chinese citation patterns from article text.

    Returns
    -------
    list[ExtractedCitation]
        Every unique label appears at most once; the first occurrence wins.
    """
    seen_labels = set()
    citations = []

    # 1. Extract [Sx] markers
    for match in SX_PATTERN.finditer(text):
        label = match.group(1)
        if label in seen_labels:
            continue
        seen_labels.add(label)
        pos = match.start()

        before_text = _text_before(text, pos, max_chars=300)
        after_text = _text_after(text, pos + len(match.group()), max_chars=150)
        page = _find_page_in_range(text, max(0, pos - 100), pos + 100)

        citations.append(ExtractedCitation(
            label=label,
            cited_text=before_text,
            context_before=before_text,
            context_after=after_text,
            page_mentioned=page,
        ))

    # 2. Extract Chinese citation patterns referencing known document titles
    if evidence_results:
        for match in CHINESE_CITATION_PATTERN.finditer(text):
            title = match.group("title")
            page = match.group("page") or ""

            matched = _match_title_to_label(title, evidence_results)
            if matched and matched not in seen_labels:
                seen_labels.add(matched)
                start = max(0, match.start() - 100)
                before = text[start:match.start()].strip()
                citations.append(ExtractedCitation(
                    label=matched,
                    cited_text=match.group(),
                    context_before=before,
                    page_mentioned=page,
                ))

    return citations


def _text_before(text: str, pos: int, max_chars: int = 300) -> str:
    """Return text immediately preceding *pos* (up to *max_chars*)."""
    start = max(0, pos - max_chars)
    before = text[start:pos].strip()
    # Snip at the last sentence boundary if there is one
    boundary = max(
        before.rfind("。"), before.rfind("！"),
        before.rfind("？"), before.rfind("\n"),
    )
    if 0 < boundary < len(before) - 1:
        before = before[boundary + 1:].strip()
    return before


def _text_after(text: str, pos: int, max_chars: int = 150) -> str:
    """Return text immediately after *pos* (up to first sentence boundary)."""
    after = text[pos:pos + max_chars].strip()
    parts = re.split(r"[。！？\n]", after, maxsplit=1)
    return parts[0].strip() if parts else after


def _find_page_in_range(text: str, start: int, end: int) -> str:
    match = PAGE_PATTERN.search(text[start:end])
    return match.group("page") if match else ""


def _match_title_to_label(title: str, evidence_results: list) -> Optional[str]:
    """Return the first evidence label whose document title overlaps with *title*."""
    if not evidence_results:
        return None
    norm = _norm(title)
    for r in evidence_results:
        doc_title = _norm(r.get("document_title", "") or r.get("original_filename", "") or "")
        if not doc_title:
            continue
        if norm in doc_title or doc_title in norm:
            return r["label"]
        # Chinese character bigram overlap
        shared = len(set(norm) & set(doc_title))
        shorter = min(len(norm), len(doc_title))
        if shorter > 0 and shared / shorter > 0.7:
            return r["label"]
    return None


def _norm(s: str) -> str:
    return s.strip().lower()

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def _text_similarity(a: str, b: str) -> float:
    """Character bigram Jaccard similarity for Chinese text."""
    if not a or not b:
        return 0.0
    a_bigrams = {a[i:i + 2] for i in range(len(a) - 1)}
    b_bigrams = {b[i:i + 2] for i in range(len(b) - 1)}
    if not a_bigrams or not b_bigrams:
        return 0.0
    intersection = a_bigrams & b_bigrams
    return len(intersection) / max(len(a_bigrams | b_bigrams), 1)


def _verify_single(citation: ExtractedCitation, evidence_by_label: dict) -> CitationVerification:
    """Check one citation against known evidence."""
    label = citation.label
    evidence = evidence_by_label.get(label)

    if not evidence:
        return CitationVerification(
            label=label, status="hallucinated",
            cited_text=citation.cited_text,
            reason=f"标签 {label} 在证据包中不存在，引用来源不可追溯",
        )

    chunk_text = evidence.get("text", "") or ""
    doc_title = (
        evidence.get("document_title", "")
        or evidence.get("original_filename", "")
        or f"文档 {evidence.get('document_id', '')}"
    )
    claimed = citation.cited_text

    # Attempt 1: exact substring match
    if claimed and len(claimed) >= 5 and claimed in chunk_text:
        return CitationVerification(
            label=label, status="verified",
            cited_text=claimed, evidence_text=chunk_text[:300],
            document_title=doc_title, confidence=1.0,
            reason=f"引用内容在 {doc_title} 中找到精确匹配",
        )

    # Attempt 2: bigram similarity
    if claimed and len(claimed) >= 5:
        sim = _text_similarity(claimed, chunk_text)
        if sim > 0.7:
            return CitationVerification(
                label=label, status="verified",
                cited_text=claimed, evidence_text=chunk_text[:300],
                document_title=doc_title, confidence=sim,
                reason=f"引用内容与 {doc_title} 原文相似度 {sim:.0%}，已通过验证",
            )
        if sim > 0.4:
            return CitationVerification(
                label=label, status="unverifiable",
                cited_text=claimed, evidence_text=chunk_text[:300],
                document_title=doc_title, confidence=sim,
                reason=f"引用内容与 {doc_title} 原文相似度仅 {sim:.0%}，需人工确认",
            )

    # Attempt 3: bigram hit rate (what fraction of claimed bigrams appear in chunk)
    if claimed and len(claimed) >= 10:
        claimed_bigrams = {claimed[i:i + 2] for i in range(len(claimed) - 1)}
        chunk_bigrams = {chunk_text[i:i + 2] for i in range(len(chunk_text) - 1)}
        if claimed_bigrams and chunk_bigrams:
            hit_rate = len(claimed_bigrams & chunk_bigrams) / len(claimed_bigrams)
            if hit_rate > 0.4:
                return CitationVerification(
                    label=label, status="unverifiable",
                    cited_text=claimed, evidence_text=chunk_text[:300],
                    document_title=doc_title, confidence=hit_rate,
                    reason=f"引用中约 {hit_rate:.0%} 关键词出现在 {doc_title} 原文中，但仍需人工确认",
                )

    # No meaningful match
    return CitationVerification(
        label=label, status="hallucinated",
        cited_text=claimed, evidence_text=chunk_text[:300],
        document_title=doc_title, confidence=0.0,
        reason=f"引用内容在 {doc_title} 原文片段中未找到匹配，可能为编造",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_citation_evidence_map(evidence_results: list) -> dict:
    """Build label → evidence-metadata lookup from evidence results.

    Returns a dict mapping ``"S1"`` → the evidence record dict so that
    downstream consumers (e.g. citation formatters) can look up metadata
    (title, author, journal, page, …) for each ``[Sx]`` label.
    """
    mapping = {}
    for r in (evidence_results or []):
        lbl = r.get("label", "")
        if lbl:
            mapping[lbl] = r
    return mapping


def verify_citations(
    article_id: int,
    snapshot_id: int = None,
    evidence_results: list = None,
) -> VerificationResult:
    """Extract and verify all citations in an article against known evidence.

    Parameters
    ----------
    article_id
        Article whose ``content`` field will be scanned.
    snapshot_id
        Optional retrieval-snapshot row from which to load evidence.
    evidence_results
        Direct list of evidence dicts (bypasses DB).

    Returns
    -------
    VerificationResult
    """
    article = ArticleRepo.get(article_id)
    if not article:
        return VerificationResult(
            grounding_status="unverified",
        )

    # Resolve evidence from snapshot if not passed directly
    if evidence_results is None and snapshot_id:
        snapshot = RetrievalSnapshotRepo.get(snapshot_id)
        if snapshot:
            raw = snapshot.get("evidence_json", "{}")
            if isinstance(raw, str):
                raw = json.loads(raw)
            evidence_results = raw.get("results", []) if isinstance(raw, dict) else []

    evidence_results = evidence_results or []
    article_text = article.get("content", "") or ""

    # Build label → evidence lookup
    evidence_by_label = {}
    for r in evidence_results:
        lbl = r.get("label", "")
        if lbl:
            evidence_by_label[lbl] = r

    extracted = extract_citations(article_text, evidence_results)

    if not extracted:
        return VerificationResult(
            grounding_status="verified",  # trivially true — no citations to verify
        )

    results = [_verify_single(c, evidence_by_label) for c in extracted]

    verified = sum(1 for r in results if r.status == "verified")
    unverifiable = sum(1 for r in results if r.status == "unverifiable")
    hallucinated = sum(1 for r in results if r.status == "hallucinated")

    if hallucinated > 0:
        grounding_status = "unverified"
    elif unverifiable > 0 and verified == 0:
        grounding_status = "unverified"
    elif unverifiable > 0:
        grounding_status = "partial"
    elif verified > 0:
        grounding_status = "verified"
    else:
        grounding_status = "not_checked"

    # Persist each citation attempt (clear old records first)
    ArticleCitationRepo.delete_by_article(article_id)
    for r in results:
        ev = evidence_by_label.get(r.label, {})
        ArticleCitationRepo.create(
            article_id=article_id,
            snapshot_id=snapshot_id or 0,
            source_label=r.label,
            document_id=ev.get("document_id", 0) if ev else 0,
            chunk_id=ev.get("chunk_id", 0) if ev else 0,
            quoted_text=r.cited_text,
            citation_text=r.evidence_text,
        )

    ArticleRepo.set_grounding(
        article_id,
        citation_summary={
            "verified": verified,
            "unverifiable": unverifiable,
            "hallucinated": hallucinated,
            "details": [
                {"label": c.label, "status": c.status, "reason": c.reason}
                for c in results
            ],
        },
        grounding_status=grounding_status,
    )

    return VerificationResult(
        citations=results,
        verified_count=verified,
        unverifiable_count=unverifiable,
        hallucinated_count=hallucinated,
        grounding_status=grounding_status,
    )


def format_report(result: VerificationResult) -> str:
    """Human-readable verification report."""
    if not result.citations:
        return "## 引用验证报告\n\n本文未检测到引用标记，无需验证。"

    icons = {"verified": "✅", "unverifiable": "⚠️", "hallucinated": "❌"}
    lines = [
        "## 引用验证报告",
        "",
        f"共检测到 {len(result.citations)} 条引用：",
        f"- ✅ 已验证：{result.verified_count}",
        f"- ⚠️ 需补证：{result.unverifiable_count}",
        f"- ❌ 疑似编造：{result.hallucinated_count}",
        f"- 整体状态：{result.grounding_status}",
        "",
    ]
    for c in result.citations:
        icon = icons.get(c.status, "❓")
        lines.append(f"{icon} **[{c.label}]** {c.reason}")
        if c.cited_text:
            lines.append(f"  - 文章引用：{c.cited_text[:180]}")
        if c.evidence_text and c.status != "hallucinated":
            lines.append(f"  - 原文片段：{c.evidence_text[:180]}")
        if c.document_title:
            lines.append(f"  - 来源文献：{c.document_title}")
        lines.append("")

    return "\n".join(lines)
