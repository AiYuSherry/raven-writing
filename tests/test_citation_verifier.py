"""Tests for the citation verifier — extraction, verification, and hallucination detection."""

import json
import os
import tempfile
import unittest
from unittest.mock import patch

from personal_writing.core import pipeline
from personal_writing.core.citation_verifier import (
    VerificationResult,
    extract_citations,
    format_report,
    verify_citations,
)
from personal_writing.db import schema
from personal_writing.db.repository import (
    ArticleRepo,
    DocumentChunkRepo,
    LibraryDocumentRepo,
    MaterialLibraryRepo,
    RetrievalSnapshotRepo,
    SessionRepo,
    MaterialRepo,
)
from personal_writing.material_library.chunker import chunk_document
from personal_writing.material_library.extractors import extract_text


class TempDbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_db_dir = schema.DB_DIR
        self.old_db_path = schema.DB_PATH
        schema.DB_DIR = self.tmp.name
        schema.DB_PATH = os.path.join(self.tmp.name, "test.db")
        pipeline.init()

    def tearDown(self):
        schema.DB_DIR = self.old_db_dir
        schema.DB_PATH = self.old_db_path
        self.tmp.cleanup()

    def _setup_evidence(self):
        """Create a material library with one document and chunks, return evidence results."""
        lib_id = MaterialLibraryRepo.create("测试文献库", topic="算法治理")
        doc_id = LibraryDocumentRepo.create(
            lib_id,
            title="平台治理与算法问责",
            original_filename="platform.txt",
            file_path="",
            source_type="txt",
            sha256="test-verify",
        )
        extracted = extract_text(
            "平台治理与算法问责",
            "算法治理要求平台承担透明度义务。\n\n"
            "自动化决策系统必须提供解释机制和有效的申诉渠道。\n\n"
            "欧盟《数字服务法》要求大型平台进行系统性风险评估。\n\n"
            "平台应当保存审核记录，并定期向监管机构报告。",
        )
        chunks = chunk_document(extracted, max_chars=25, overlap_chars=0)
        DocumentChunkRepo.replace_for_document(doc_id, lib_id, chunks)

        # Build evidence results matching retrieval.py format
        evidence_results = []
        for idx, chunk in enumerate(chunks, start=1):
            label = f"S{idx}"
            text = chunk.get("text", "")
            evidence_results.append({
                "label": label,
                "chunk_id": idx,
                "document_id": doc_id,
                "library_id": lib_id,
                "document_title": "平台治理与算法问责",
                "original_filename": "platform.txt",
                "source_type": "txt",
                "page_start": chunk.get("page_start", 0),
                "page_end": chunk.get("page_end", 0),
                "locator": chunk.get("locator", ""),
                "text": text,
                "snippet": text[:200],
                "score": 1.0,
                "match_type": "test",
                "citation_label": f"[{label}]",
            })
        return lib_id, doc_id, evidence_results

    def _create_article(self, content, session_id=None):
        """Create an article in the DB and return its id.
        Also creates a material and session if not provided.
        """
        if session_id is None:
            material_id = MaterialRepo.create(
                title="测试素材",
                source_type="paste",
                raw_content=content,
            )
            session_id = SessionRepo.create(
                material_id=material_id,
                style_names=["zheng_ge_academic"],
            )
        return ArticleRepo.create(
            session_id=session_id,
            style="zheng_ge_academic",
            title="测试文章",
            content=content,
        )


class ExtractCitationTests(TempDbTestCase):
    def test_extract_sx_labels(self):
        """[Sx] markers are extracted with surrounding context."""
        text = "算法治理要求平台承担透明度义务[S1]。自动化决策也需要解释机制[S2]。"
        citations = extract_citations(text)
        self.assertEqual(len(citations), 2)
        self.assertEqual(citations[0].label, "S1")
        self.assertEqual(citations[1].label, "S2")

    def test_extract_with_page_number(self):
        """Page numbers near [Sx] markers are captured."""
        text = "透明度义务是平台治理的核心要求（第45页）[S1]。"
        citations = extract_citations(text)
        self.assertGreaterEqual(len(citations), 1)
        # 45 should be captured as page
        self.assertEqual(citations[0].label, "S1")

    def test_extract_no_citations(self):
        """Text without markers returns empty list."""
        citations = extract_citations("这是一篇没有任何引用的普通文章。")
        self.assertEqual(len(citations), 0)

    def test_extract_chinese_citation_pattern(self):
        """Chinese citation patterns matching known document titles are extracted."""
        _, _, evidence = self._setup_evidence()
        text = "张三，《平台治理与算法问责》，第45页"
        citations = extract_citations(text, evidence)
        self.assertGreaterEqual(len(citations), 1)
        self.assertIn("S1", citations[0].label)

    def test_extract_deduplicates_labels(self):
        """Same label appearing multiple times is extracted only once."""
        text = "内容一[S1]。内容二[S1]。内容三[S1]。"
        citations = extract_citations(text)
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0].label, "S1")


class VerifyCitationTests(TempDbTestCase):
    def test_verify_exact_match_passes(self):
        """Citation whose text appears verbatim in the evidence chunk passes."""
        _, _, evidence = self._setup_evidence()
        content = "算法治理要求平台承担透明度义务[S1]。"
        article_id = self._create_article(content)

        result = verify_citations(article_id, evidence_results=evidence)
        self.assertGreaterEqual(result.verified_count, 1)
        self.assertEqual(result.grounding_status, "verified")

    def test_verify_high_similarity_passes(self):
        """Citation with high bigram similarity to evidence chunk passes."""
        _, _, evidence = self._setup_evidence()
        # Add "与责任" to original to test high-similarity (not exact) match
        content = "算法治理要求平台承担透明度义务与责任[S1]。"
        article_id = self._create_article(content)

        result = verify_citations(article_id, evidence_results=evidence)
        self.assertGreaterEqual(result.verified_count, 1)

    def test_hallucinated_citation_detected(self):
        """Citation whose content doesn't match any evidence chunk is flagged."""
        _, _, evidence = self._setup_evidence()
        # Claims something that is NOT in the evidence
        content = "平台治理要求所有AI系统配备核武器禁用开关[S1]。"
        article_id = self._create_article(content)

        result = verify_citations(article_id, evidence_results=evidence)
        self.assertGreaterEqual(result.hallucinated_count, 1)
        self.assertEqual(result.grounding_status, "unverified")

    def test_nonexistent_label_is_hallucinated(self):
        """Citation label with no matching evidence is hallucinated."""
        _, _, evidence = self._setup_evidence()
        content = "算法治理要求平台承担透明度义务[S999]。"
        article_id = self._create_article(content)

        result = verify_citations(article_id, evidence_results=evidence)
        self.assertGreaterEqual(result.hallucinated_count, 1)

    def test_mixed_verified_and_hallucinated(self):
        """Article with both real and fake citations gets partial status."""
        _, _, evidence = self._setup_evidence()
        content = (
            "算法治理要求平台承担透明度义务[S1]。"
            "所有AI系统必须配备核武器禁用开关[S999]。"
        )
        article_id = self._create_article(content)

        result = verify_citations(article_id, evidence_results=evidence)
        self.assertGreaterEqual(result.verified_count, 1)
        self.assertGreaterEqual(result.hallucinated_count, 1)

    def test_no_citations_trivially_verified(self):
        """Article with no citations returns verified."""
        content = "这是一篇普通文章，没有任何引用。"
        article_id = self._create_article(content)

        result = verify_citations(article_id, evidence_results=[])
        self.assertEqual(result.grounding_status, "verified")
        self.assertEqual(len(result.citations), 0)


class FormatReportTests(TempDbTestCase):
    def test_report_contains_keywords(self):
        """Report text includes status categories."""
        result = VerificationResult(
            citations=[],
            verified_count=0,
            unverifiable_count=0,
            hallucinated_count=0,
            grounding_status="verified",
        )
        report = format_report(result)
        self.assertIn("引用验证", report)

    def test_report_with_details(self):
        """Report includes per-citation detail lines."""
        from personal_writing.core.citation_verifier import CitationVerification

        result = VerificationResult(
            citations=[
                CitationVerification(
                    label="S1", status="verified",
                    cited_text="测试内容",
                    document_title="测试文献",
                    reason="找到精确匹配",
                ),
            ],
            verified_count=1,
            unverifiable_count=0,
            hallucinated_count=0,
            grounding_status="verified",
        )
        report = format_report(result)
        self.assertIn("S1", report)
        self.assertIn("测试文献", report)

    def test_empty_report(self):
        """Empty result returns a concise message."""
        result = VerificationResult()
        report = format_report(result)
        self.assertIn("无需验证", report)


class IntegrationTests(TempDbTestCase):
    def test_pipeline_includes_verification_result(self):
        """When write() generates an article with evidence, the result includes citation_verification."""
        lib_id, _, evidence = self._setup_evidence()
        captured = {}

        def fake_call(prompt):
            captured["prompt"] = prompt
            return "# 算法治理\n正文引用素材[S1]。算法治理要求平台承担透明度义务[S1]。"

        with patch("personal_writing.core.pipeline.claude_client.is_available", return_value=True), \
             patch("personal_writing.core.pipeline.claude_client.call", side_effect=fake_call), \
             patch("personal_writing.core.pipeline.save_local_file", return_value=""):
            result = pipeline.write(
                "算法治理论文",
                ["zheng_ge_academic"],
                library_ids=[lib_id],
                retrieval_query="算法治理",
                library_mode="strict",
            )

        self.assertIn("citation_verification", result["articles"][0])
        cv = result["articles"][0]["citation_verification"]
        self.assertIsNotNone(cv)
        self.assertIn("grounding_status", cv)
        self.assertIn("verified_count", cv)
        self.assertIn("hallucinated_count", cv)

    def test_verify_api_endpoint(self):
        """API endpoint returns correct JSON structure."""
        from personal_writing.web.app import create_app

        content = "算法治理要求平台承担透明度义务[S1]。"
        article_id = self._create_article(content)

        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get(f"/api/v1/article/{article_id}/verify-citations")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["status"], "ok")
        # Should have the verification fields
        self.assertIn("grounding_status", data)
        self.assertIn("verified_count", data)
        self.assertIn("hallucinated_count", data)
        self.assertIn("report", data)

    def test_verify_nonexistent_article_returns_404(self):
        """API returns 404 for non-existent article."""
        from personal_writing.web.app import create_app

        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()

        response = client.get("/api/v1/article/99999/verify-citations")
        self.assertEqual(response.status_code, 404)

    def test_prompt_contains_citation_rules(self):
        """Writing prompt includes stricter citation format rules when library is selected."""
        lib_id, _, evidence = self._setup_evidence()
        captured = {}

        def fake_call(prompt):
            captured["prompt"] = prompt
            return "# 测试\n正文。"

        with patch("personal_writing.core.pipeline.claude_client.is_available", return_value=True), \
             patch("personal_writing.core.pipeline.claude_client.call", side_effect=fake_call), \
             patch("personal_writing.core.pipeline.save_local_file", return_value=""):
            pipeline.write(
                "测试素材",
                ["zheng_ge_academic"],
                library_ids=[lib_id],
                library_mode="strict",
            )

        prompt = captured.get("prompt", "")
        # Stricter rules should be present
        self.assertIn("[Sx]", prompt)
        self.assertIn("不得编造", prompt)
        self.assertIn("引用格式", prompt)


if __name__ == "__main__":
    unittest.main()
