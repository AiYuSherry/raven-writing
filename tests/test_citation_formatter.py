"""Tests for citation footnote formatter — replacing [Sx] with academic footnotes."""

import unittest

from personal_writing.core.citation_formatter import format_article_footnotes


class FormatArticleFootnotesTests(unittest.TestCase):
    """Unit tests for the formatting logic with mocked evidence."""

    def _evidence(self, label: str, **overrides) -> dict:
        """Build a standard evidence-result dict with sensible defaults."""
        base = {
            "label": label,
            "document_title": "行政处罚的主观要件",
            "original_filename": "paper.txt",
            "source_type": "zotero",
            "page_start": 45,
            "page_end": 48,
            "locator": "p.45",
            "snippet": "主观要件包括故意和过失…",
            "text": "主观要件包括故意和过失两种形态。",
            "score": 0.95,
            "match_type": "fts",
            "citation_label": f"[{label}] 行政处罚的主观要件",
        }
        base.update(overrides)
        return base

    # ── Full metadata ──────────────────────────────────────────────────

    def test_full_journal_article(self):
        """Evidence with author, title, journal, year yields a full footnote."""
        ev = self._evidence(
            "S1",
            author="张三",
            authors='["张三"]',
            year="2023",
            publication_title="法学研究",
        )
        body, notes = format_article_footnotes(
            "主观要件包括故意和过失两种形态[S1]。",
            [ev],
        )
        self.assertIn("[1]", body)
        self.assertNotIn("[S1]", body)
        self.assertIn("张三", notes)
        self.assertIn("行政处罚的主观要件", notes)
        self.assertIn("法学研究", notes)
        self.assertIn("2023年", notes)

    def test_two_authors(self):
        """Two authors are joined with Chinese enumeration comma."""
        ev = self._evidence(
            "S1",
            author="张三;李四",
            authors='["张三", "李四"]',
            year="2023",
            publication_title="法学研究",
        )
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("张三、李四", notes)

    def test_three_plus_authors_uses_et_al(self):
        """Three+ authors show only the first plus 等."""
        ev = self._evidence(
            "S1",
            author="甲;乙;丙",
            authors='["甲", "乙", "丙"]',
            year="2023",
            publication_title="法学研究",
        )
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("甲等", notes)

    # ── Partial metadata ───────────────────────────────────────────────

    def test_no_journal(self):
        """Without publication_title, format falls back to simpler style."""
        ev = self._evidence("S1", authors='["张三"]', year="2023", publication_title="")
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("张三", notes)
        self.assertIn("行政处罚的主观要件", notes)
        self.assertIn("2023年", notes)

    def test_no_author_no_journal(self):
        """Only title available produces a minimal footnote."""
        ev = self._evidence(
            "S1",
            author="",
            authors="[]",
            year="",
            publication_title="",
        )
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("行政处罚的主观要件", notes)
        self.assertNotIn("张三", notes)
        self.assertNotIn("2023年", notes)

    # ── Missing / hallucinated labels ─────────────────────────────────

    def test_label_without_evidence(self):
        """Label not in evidence map → ”需补证“ marker."""
        _, notes = format_article_footnotes("[S999]", [])
        self.assertIn("需补证", notes)
        self.assertIn("S999", notes)

    def test_label_without_metadata(self):
        """Evidence record that is missing document_title → fallback."""
        ev = {"label": "S1", "document_title": ""}
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("需补证", notes)

    # ── Multiple citations ─────────────────────────────────────────────

    def test_multiple_unique_labels(self):
        """Multiple different [Sx] labels produce sequential [1][2] markers."""
        ev1 = self._evidence("S1", authors='["张三"]', year="2023")
        ev2 = self._evidence("S2", authors='["李四"]', year="2022",
                             document_title="行政裁量的司法审查",
                             publication_title="中国法学")
        body, notes = format_article_footnotes(
            "观点一[S1]。观点二[S2]。",
            [ev1, ev2],
        )
        self.assertIn("[1]", body)
        self.assertIn("[2]", body)
        self.assertIn("张三", notes)
        self.assertIn("李四", notes)

    def test_duplicate_label(self):
        """Same [Sx] appearing multiple times → same [N] each time."""
        ev = self._evidence("S1", authors='["张三"]', year="2023")
        body, notes = format_article_footnotes(
            "开头[S1]。中间[S1]。结尾[S1]。",
            [ev],
        )
        self.assertEqual(body.count("[1]"), 3)
        self.assertEqual(body.count("[2]"), 0)

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_no_citations(self):
        """Plain text with no [Sx] markers is returned unchanged."""
        body, notes = format_article_footnotes("这是一篇普通文章。", [])
        self.assertEqual(body, "这是一篇普通文章。")
        self.assertEqual(notes, "")

    def test_no_evidence(self):
        """Citations with no evidence → marker preserved but footnote is fallback."""
        body, notes = format_article_footnotes("文中引用了某观点[S1]。")
        # Body: [Sx] should become [1]
        self.assertIn("[1]", body)
        self.assertNotIn("[S1]", body)
        # Notes: fallback message
        self.assertIn("需补证", notes)

    def test_empty_content(self):
        """Empty string input returns empty."""
        body, notes = format_article_footnotes("", [])
        self.assertEqual(body, "")
        self.assertEqual(notes, "")

    def test_authors_field_is_json_string(self):
        """authors as a JSON-encoded string is parsed correctly."""
        ev = self._evidence(
            "S1",
            authors='["王五", "赵六", "孙七"]',
            author="",
            year="2024",
            publication_title="中外法学",
        )
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("王五等", notes)
        self.assertIn("中外法学", notes)

    def test_page_from_locator(self):
        """Page number from locator field appears in footnote."""
        ev = self._evidence(
            "S1",
            authors='["张三"]',
            year="2023",
            publication_title="法学研究",
            locator="p.33",
            page_start=33,
        )
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("33页", notes)

    def test_page_range(self):
        """Page range from page_start/page_end appears as X—Y页."""
        ev = self._evidence(
            "S1",
            locator="",
            page_start=100,
            page_end=120,
        )
        _, notes = format_article_footnotes("[S1]", [ev])
        self.assertIn("100", notes)
        self.assertIn("120", notes)


if __name__ == "__main__":
    unittest.main()
